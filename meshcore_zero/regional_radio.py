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
    def __init__(self, *args, region='US', **kwargs):
        self.region=region
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
        if self.region!='JP': return await super().send(data)
        # Separate lock spans the base driver's lock and the final RX restore.
        async with self._regional_lock:
            try: return await super().send(data)
            finally: self._last_regional_tx=time.monotonic()
