package th.co.thanabunyapat.erp

/** Pure ESC/POS packet construction: safe to test without an Android emulator. */
object EscPosProtocol {
    fun initialise(): ByteArray = byteArrayOf(0x1b, 0x40)

    fun rasterHeader(bytesPerRow: Int, rows: Int): ByteArray {
        require(bytesPerRow in 1..255) { "bytesPerRow must fit in ESC/POS low byte" }
        require(rows in 1..255) { "rows must fit in ESC/POS low byte" }
        return byteArrayOf(0x1d, 0x76, 0x30, 0x00, bytesPerRow.toByte(), 0x00, rows.toByte(), 0x00)
    }

    fun feed(): ByteArray = byteArrayOf(10, 10, 10)
}
