# WMS PDA Android App

将 PDA 扫描页面打包为 Android WebView 应用。

## 构建步骤

1. 安装 Android Studio
2. 打开 `android-app` 目录作为项目
3. 修改 `MainActivity.java` 中的 `SERVER_URL` 为你的服务器地址
4. 点击 Build > Generate Signed APK 生成发布包

## 功能

- WebView 加载 PDA 扫描页面
- 支持摄像头拍照上传
- 支持文件选择上传
- 全屏无标题栏界面
- 支持 HTTP 明文流量（用于内网部署）

## 服务器地址配置

默认地址：`http://43.161.231.19/pda.html`

如需修改，编辑 `MainActivity.java` 中的 `SERVER_URL` 常量。
