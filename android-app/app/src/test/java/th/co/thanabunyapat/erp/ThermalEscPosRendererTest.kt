package th.co.thanabunyapat.erp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ThermalEscPosRendererTest {
    @Test
    fun testReceiptStartsWithInitializeAndEndsWithFeed() {
        val bytes = ThermalEscPosRenderer.testReceipt("PT-280_7AA9")

        assertTrue(bytes.size > 100)
        assertEquals(0x1b, bytes[0].toInt() and 0xff)
        assertEquals(0x40, bytes[1].toInt() and 0xff)
        assertEquals(10, bytes[bytes.lastIndex].toInt())
    }
}
