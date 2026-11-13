package th.co.thanabunyapat.erp

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import java.io.ByteArrayOutputStream

/** Renders a small, test-only receipt to 58 mm ESC/POS raster commands. */
object ThermalEscPosRenderer {
    private const val width = 384
    private const val lineHeight = 26

    fun testReceipt(printerName: String): ByteArray = raster(
        listOf(
            "ธนาบุณยภัทร ERP",
            "หน้าทดสอบเครื่องพิมพ์ 58 มม.",
            "ข้อมูลทดสอบเท่านั้น",
            "เครื่องพิมพ์: $printerName",
            "พิมพ์จาก Android APK",
        ),
    )

    fun raster(lines: List<String>): ByteArray {
        val rows = lines.flatMap(::wrap)
        val bitmap = Bitmap.createBitmap(width, rows.size * lineHeight + 24, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.WHITE)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.BLACK
            textSize = 20f
            typeface = Typeface.create("sans", Typeface.NORMAL)
        }
        rows.forEachIndexed { index, row -> canvas.drawText(row, 8f, 21f + index * lineHeight, paint) }

        val output = ByteArrayOutputStream().apply { write(EscPosProtocol.initialise()) }
        val stride = width / 8
        for (top in 0 until bitmap.height step 96) {
            val height = minOf(96, bitmap.height - top)
            output.write(EscPosProtocol.rasterHeader(stride, height))
            for (y in top until top + height) {
                for (byteX in 0 until stride) {
                    var value = 0
                    for (bit in 0..7) {
                        if (bitmap.getPixel(byteX * 8 + bit, y) != Color.WHITE) value = value or (0x80 shr bit)
                    }
                    output.write(value)
                }
            }
        }
        output.write(EscPosProtocol.feed())
        bitmap.recycle()
        return output.toByteArray()
    }

    private fun wrap(line: String): List<String> {
        val paint = Paint().apply { textSize = 20f }
        val rows = mutableListOf<String>()
        var current = ""
        for (character in line) {
            if (current.isNotEmpty() && paint.measureText(current + character) > width - 16) {
                rows += current
                current = ""
            }
            current += character
        }
        if (current.isNotEmpty()) rows += current
        return rows.ifEmpty { listOf("") }
    }
}
