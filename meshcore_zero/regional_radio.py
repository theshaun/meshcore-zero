"""Physical transmit guards, including engine-generated ACKs and retries.

Japan is experimental: these host-side controls are not Giteki certification.
The GPIO/radio implementation remains the vendored openHop driver.
"""
import asyncio
import random
import time

async def wait_clear(sample, receiving=lambda: False, *, duration=.005, timeout=4.0, threshold=-80):
    """Require repeated energy samples over a full clear window; never force TX."""
    deadline=time.monotonic()+timeout
    clear_since=None
    delays=[]
    while time.monotonic()<deadline:
        value=sample()  # An unavailable/invalid read fails closed.
        if value is None or not -127.5<=value<0:
            raise RuntimeError('JP RSSI sensing unavailable')
        now=time.monotonic()
        if value>=threshold or receiving():
            clear_since=None
            delay=min(random.uniform(.1,.3),max(0,deadline-now))
            delays.append(round(delay*1000))
            await asyncio.sleep(delay)
        else:
            if clear_since is None: clear_since=now
            if now-clear_since>=duration: return delays
            await asyncio.sleep(.001)
    raise RuntimeError('JP channel busy; transmission cancelled')

class RegionalRadioMixin:
    def __init__(self, *args, region='US', airtime_budget=None, **kwargs):
        self.region=region
        self.airtime_budget=airtime_budget
        self._packet_airtime=0.0
        self.airtime_error=''
        self._regional_lock=asyncio.Lock()
        self._last_regional_tx=0.0
        super().__init__(*args, **kwargs)

    def _calculate_tx_timeout(self, packet_length):
        if self.region=='JP':
            from openhop_core.protocol.packet_utils import calculate_lora_airtime_ms
            airtime=calculate_lora_airtime_ms(packet_length,self.spreading_factor,self.bandwidth,self.coding_rate,self.preamble_length)
            if self.tx_power>13 or self.frequency!=920800000 or self.bandwidth!=125000:
                raise RuntimeError('Invalid Japan radio configuration')
            if airtime>=4000:
                raise ValueError('JP packet exceeds 4-second airtime limit')
        return super()._calculate_tx_timeout(packet_length)

    async def _prepare_radio_for_tx(self):
        if self.region!='JP': return await super()._prepare_radio_for_tx()
        await asyncio.sleep(max(0,self._last_regional_tx+.05-time.monotonic()))
        # Re-arm RX explicitly; the base helper logs and swallows RX errors.
        self._control_tx_rx_pins(tx_mode=False)
        self.lora.setStandby(self.lora.STANDBY_RC)
        self.lora.clearIrqStatus(0xffff)
        mask=self._get_rx_irq_mask()
        self.lora.setDioIrqParams(mask,mask,self.lora.IRQ_NONE,self.lora.IRQ_NONE)
        self.lora.request(self.lora.RX_CONTINUOUS)
        await asyncio.sleep(.01)
        def sample():
            raw=self.lora.getRssiInst()
            return None if raw is None else -float(raw)/2
        delays=await wait_clear(sample,self.is_receiving_packet)
        self.lora.setStandby(self.lora.STANDBY_RC)
        if self.lora.busyCheck(): raise RuntimeError('JP radio busy; transmission cancelled')
        self._control_tx_rx_pins(tx_mode=True)
        self._rx_activity_at=self._rx_header_at=0.0
        self._tx_done_event.clear(); self._rx_done_event.clear()
        await self._drain_pending_rx_irq_before_buffer_reuse()
        return True,delays

    async def send(self,data):
        # Serialize the actual packet size with its eventual SetTx reservation.
        async with self._regional_lock:
            self.airtime_error=''
            from openhop_core.protocol.packet_utils import calculate_lora_airtime_ms
            self._packet_airtime=calculate_lora_airtime_ms(
                len(data),self.spreading_factor,self.bandwidth,
                self.coding_rate,self.preamble_length)/1000
            try: return await super().send(data)
            finally:
                if self.region=='JP': self._last_regional_tx=time.monotonic()
                self._packet_airtime=0.0

    async def _execute_transmission(self,*args,**kwargs):
        frequency=self.frequency
        if 863000000<=frequency<=870000000:
            # All current European API presets fit the 10% sub-band. For a
            # future entry outside it, retain a conservative 0.1% hourly cap.
            half=self.bandwidth/2
            limit=360 if 869400000<=frequency-half and frequency+half<=869650000 else 3.6
            if self.airtime_budget is None:
                raise RuntimeError('Hourly airtime accounting unavailable')
            # Commit before SetTx, after LBT/privacy checks. An uncertain TX
            # failure remains charged; every retry/ACK passes this same guard.
            try:self.airtime_budget.reserve(self._packet_airtime,limit=limit)
            except ValueError as exc:
                self.airtime_error=str(exc)
                raise
        return await super()._execute_transmission(*args,**kwargs)

    async def _restore_rx_mode(self):
        # The base driver only clears this on successful TX. A budget/privacy
        # rejection happens after buffer ownership was set; release it before
        # RX is rearmed so incoming terminal IRQs are delivered on failure too.
        self._tx_buffer_busy=False
        return await super()._restore_rx_mode()
