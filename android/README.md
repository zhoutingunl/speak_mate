# SpeakMate Android(WebView 套壳)

把 SpeakMate Web 应用包成 Android App。**它是一个瘦客户端**:加载一台运行中的 SpeakMate 服务器(你的电脑/服务器),后端与 AI key 仍在服务端。

## 为什么这样设计
- 后端是 Python(Flask)+ MiniMax/Azure/百炼 key,**无法塞进 APK**,只能跑在服务器。
- Android System WebView **没有 Web Speech API**,所以网页会自动走**服务端百炼 ASR**(`/api/transcribe`)——这正是之前做兜底的意义。
- 录音(`getUserMedia`)要求**安全上下文**,因此服务器需用 **HTTPS**(自签即可),App 已放行自签证书。

## 一、启动服务器(供手机访问,HTTPS)
在项目根目录:
```bash
# 需要 cryptography 以启用自签 HTTPS:pip install cryptography
HOST=0.0.0.0 SPEAKMATE_HTTPS=1 python app.py
# 控制台会打印 https://0.0.0.0:5001
```
查到电脑的局域网 IP(`ipconfig getifaddr en0`),手机与电脑连同一 WiFi,App 里填 `https://<电脑IP>:5001`。

## 二、构建 APK
需 Android SDK(platform 34、build-tools 34)与 JDK 17+(Android Studio 自带 JBR 21)。

**方式 A:Android Studio(推荐)**
打开 `android/` 目录,等 Gradle Sync 完成,菜单 Build → Build APK(或运行到手机)。

**方式 B:命令行**
```bash
cd android
# 用 Android Studio 自带 JDK,避免系统 Java 8
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew assembleDebug
# 产物:app/build/outputs/apk/debug/app-debug.apk
```
首次构建会从阿里云镜像拉取 AGP/androidx 依赖。

安装:`adb install -r app/build/outputs/apk/debug/app-debug.apk`,或把 APK 传到手机直接装(需允许“未知来源”)。

## 三、使用
1. 打开 App,首次填入服务器地址 `https://<电脑IP>:5001`,点“连接”;
2. 允许麦克风权限;
3. 选场景 → 按住说话(Android 自动用百炼 ASR)→ 看发音分/纠错 → 课后总结/Dashboard。

返回键:网页可后退则后退;在首页按返回会弹出“修改服务器地址/退出”。

## 关键实现
- `MainActivity.kt`:WebView 配置(JS、DOM storage、自动播放)、`onPermissionRequest` 放行麦克风、`onReceivedSslError` 放行自签证书、服务器地址持久化(SharedPreferences)。
- `AndroidManifest.xml`:`INTERNET` / `RECORD_AUDIO` / `MODIFY_AUDIO_SETTINGS` 权限;`usesCleartextTraffic` + `network_security_config`。
- 包名 `com.speakmate.app`,minSdk 24,targetSdk 34。

> 安全提示:放行自签证书与明文流量仅为局域网 demo 方便;正式发布应使用受信证书并收紧网络安全配置。
