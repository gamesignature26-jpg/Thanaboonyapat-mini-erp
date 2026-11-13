package th.co.thanabunyapat.erp

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

/** Test APK: loads only the approved staging app and prints an explicit test receipt via Bluetooth Classic. */
class MainActivity : AppCompatActivity() {
    private val printer = BluetoothClassicPrinter(BluetoothAdapter.getDefaultAdapter())
    private val background = Executors.newSingleThreadExecutor()
    private lateinit var webView: WebView
    private lateinit var printerStatus: TextView

    private val bluetoothPermission = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants ->
        if (grants.values.all { it }) choosePrinter() else toast("ต้องอนุญาต Bluetooth เพื่อค้นหาและพิมพ์")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(createContent())
        configureWebView()
        webView.loadUrl(STAGING_URL)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.setSupportMultipleWindows(false)
        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return !request.url.toString().startsWith(STAGING_URL)
            }
        }
        webView.addJavascriptInterface(NativeTestBridge(), "ThanabunyapatNative")
    }

    private fun createContent(): LinearLayout {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(13, 52, 73))
        }
        val toolbar = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(20, 14, 20, 14)
        }
        val title = TextView(this).apply {
            text = "ธนาบุณยภัทร ERP · รุ่นทดสอบ"
            setTextColor(Color.WHITE)
            textSize = 18f
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        val connect = Button(this).apply {
            text = "เครื่องพิมพ์ 58 มม."
            setOnClickListener { requestBluetoothThenChoose() }
        }
        toolbar.addView(title)
        toolbar.addView(connect)
        printerStatus = TextView(this).apply {
            text = "ยังไม่ได้เชื่อมต่อเครื่องพิมพ์"
            setTextColor(Color.WHITE)
            setPadding(20, 0, 20, 12)
        }
        webView = WebView(this)
        root.addView(toolbar)
        root.addView(printerStatus)
        root.addView(webView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        return root
    }

    private fun requestBluetoothThenChoose() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED
        ) {
            bluetoothPermission.launch(arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN))
        } else choosePrinter()
    }

    @SuppressLint("MissingPermission")
    private fun choosePrinter() {
        val devices = printer.pairedDevices()
        if (devices.isEmpty()) {
            toast("ไม่พบเครื่องที่จับคู่ไว้ กรุณาจับคู่ PT-280 ในการตั้งค่า Bluetooth ของ Android ก่อน")
            return
        }
        val names = devices.map { "${it.name ?: "ไม่ทราบชื่อ"}\n${it.address}" }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("เลือกเครื่องพิมพ์ Bluetooth Classic")
            .setItems(names) { _, index -> connectAndPrintTest(devices[index]) }
            .setNegativeButton("ยกเลิก", null)
            .show()
    }

    private fun connectAndPrintTest(device: android.bluetooth.BluetoothDevice) {
        printerStatus.text = "กำลังเชื่อมต่อ ${device.name ?: device.address}…"
        background.execute {
            try {
                printer.connect(device)
                val name = printer.connectedName ?: device.address
                printer.print(ThermalEscPosRenderer.testReceipt(name))
                runOnUiThread {
                    printerStatus.text = "ส่งหน้าทดสอบไปยัง $name แล้ว"
                    toast("ส่งหน้าทดสอบพิมพ์แล้ว")
                }
            } catch (error: Exception) {
                printer.close()
                runOnUiThread {
                    printerStatus.text = "พิมพ์ไม่สำเร็จ"
                    toast("พิมพ์ไม่สำเร็จ: ${error.message ?: "ไม่ทราบสาเหตุ"}")
                }
            }
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        printer.close()
        background.shutdownNow()
        webView.destroy()
        super.onDestroy()
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    inner class NativeTestBridge {
        @JavascriptInterface
        fun requestPrinterTest() = runOnUiThread { requestBluetoothThenChoose() }
    }

    private companion object {
        const val STAGING_URL = "https://thanabunyapat-erp-flow-staging-pfuv.onrender.com/"
    }
}
