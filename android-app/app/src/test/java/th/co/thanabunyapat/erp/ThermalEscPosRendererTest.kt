package th.co.thanabunyapat.erp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ThermalEscPosRendererTest {
    @Test
    fun escPosCommandsHaveExpectedBinaryFormat() {
        assertEquals(listOf(0x1b, 0x40), EscPosProtocol.initialise().map { it.toInt() and 0xff })
        assertEquals(
            listOf(0x1d, 0x76, 0x30, 0, 48, 0, 96, 0),
            EscPosProtocol.rasterHeader(48, 96).map { it.toInt() and 0xff },
        )
        assertTrue(EscPosProtocol.feed().all { it.toInt() == 10 })
    }
}
