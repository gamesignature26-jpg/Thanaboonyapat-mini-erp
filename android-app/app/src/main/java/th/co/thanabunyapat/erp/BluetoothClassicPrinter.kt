package th.co.thanabunyapat.erp

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import java.io.IOException
import java.util.UUID

/** Bluetooth Classic SPP transport used by common portable 58 mm ESC/POS printers. */
class BluetoothClassicPrinter(private val adapter: BluetoothAdapter?) {
    private var socket: BluetoothSocket? = null
    var connectedName: String? = null
        private set

    @SuppressLint("MissingPermission")
    fun pairedDevices(): List<BluetoothDevice> = adapter?.bondedDevices?.sortedBy { it.name ?: it.address } ?: emptyList()

    @SuppressLint("MissingPermission")
    @Throws(IOException::class)
    fun connect(device: BluetoothDevice) {
        close()
        check(adapter?.isEnabled == true) { "กรุณาเปิด Bluetooth ก่อน" }
        val next = device.createRfcommSocketToServiceRecord(SPP_UUID)
        adapter.cancelDiscovery()
        next.connect()
        socket = next
        connectedName = device.name ?: device.address
    }

    @Throws(IOException::class)
    fun print(bytes: ByteArray) {
        val active = socket ?: error("ยังไม่ได้เชื่อมต่อเครื่องพิมพ์")
        active.outputStream.use { output ->
            output.write(bytes)
            output.flush()
        }
        // A printer remains paired but most sockets close after the job; force explicit reconnect for the next job.
        socket = null
    }

    fun close() {
        try { socket?.close() } catch (_: IOException) { }
        socket = null
        connectedName = null
    }

    companion object {
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }
}
