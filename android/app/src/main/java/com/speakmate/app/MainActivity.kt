package com.speakmate.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.net.http.SslError
import android.os.Bundle
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * SpeakMate 的 WebView 套壳:加载一台可配置的 SpeakMate 服务器。
 *
 * 关键点:
 * - 录音(getUserMedia)需安全上下文 → 服务器用 HTTPS(自签),这里放行自签证书;
 * - onPermissionRequest 放行 WebView 的麦克风请求;
 * - Android WebView 无 Web Speech API,网页会自动走服务端百炼 ASR(详见前端逻辑)。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private val prefs by lazy { getSharedPreferences("speakmate", MODE_PRIVATE) }

    private val askMic = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission()
    ) { /* 结果不阻塞流程;onPermissionRequest 会再校验 */ }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            askMic.launch(Manifest.permission.RECORD_AUDIO)
        }

        configureWebView()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else showServerDialog()
            }
        })

        val url = prefs.getString("server_url", null)
        if (url.isNullOrBlank()) showServerDialog() else web.loadUrl(url)
    }

    private fun configureWebView() {
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false // 允许 TTS 自动播放
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            cacheMode = WebSettings.LOAD_DEFAULT
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                // 仅放行音频采集,且 App 已持有 RECORD_AUDIO
                val wantAudio = request.resources.any {
                    it == PermissionRequest.RESOURCE_AUDIO_CAPTURE
                }
                val hasPerm = ContextCompat.checkSelfPermission(
                    this@MainActivity, Manifest.permission.RECORD_AUDIO
                ) == PackageManager.PERMISSION_GRANTED
                if (wantAudio && hasPerm) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else {
                    request.deny()
                    if (!hasPerm) askMic.launch(Manifest.permission.RECORD_AUDIO)
                }
            }
        }

        web.webViewClient = object : WebViewClient() {
            // 自签证书:demo 场景下放行(生产应换正式证书)
            override fun onReceivedSslError(
                view: WebView?, handler: SslErrorHandler?, error: SslError?
            ) {
                handler?.proceed()
            }
        }
    }

    /** 输入/修改服务器地址(SharedPreferences 持久化,改完即加载)。 */
    private fun showServerDialog() {
        val input = EditText(this).apply {
            hint = "https://192.168.x.x:5001"
            setText(prefs.getString("server_url", "https://192.168.1.10:5001"))
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.server_prompt)
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("连接") { _, _ ->
                val url = input.text.toString().trim()
                if (url.isNotBlank()) {
                    prefs.edit().putString("server_url", url).apply()
                    web.loadUrl(url)
                }
            }
            .setNegativeButton("退出") { _, _ -> finish() }
            .show()
    }
}
