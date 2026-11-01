# CloneProfileCompatibility

[源码仓库](https://github.com/mumingluan/CloneProfileCompatibility) · [下载](https://github.com/mumingluan/CloneProfileCompatibility/releases)

独立的 LSPosed 兼容模块，允许主用户上的 AxuanMDM Device Owner 与 OPPO 应用分身共存。包名沿用 `com.axuan.mdmcloneprofilecompatibility`，签名一致时可覆盖升级原来的 1.0。

## 作用范围

适配依据是 OPPO PHT110、Android 16 / ColorOS `PHT110_16.0.5.1301(CN01)`。模块只加载到系统框架进程，并检查主用户 0 的 Device Owner 是否为 `com.axuan.mdm`。

满足条件时，清除主用户的 `no_add_clone_profile` 基础限制，并拦截 DevicePolicyManagerService 在启动及设置设备所有者时自动写入的同名限制。自动写入拦截仅针对用户 0 和 OPPO 分身用户 999。

运行需要支持系统框架作用域的 LSPosed。其他 ROM 的系统方法签名和限制策略可能不同，需要对应的适配验证。

## 安装

1. 从 Releases 下载 APK 并安装。
2. 在 LSPosed 中启用，作用域选择「系统框架（android）」。
3. 重启后检查应用分身和模块日志。

日志标签为 `AxuanMDMCloneProfile`。成功加载时输出 `v1.0.1 hooks installed in system_server`；拦截自动限制时输出 `Allowed clone profile`。可通过以下命令检查主用户的当前限制：

```sh
pm get-user-restriction --user 0 no_add_clone_profile
```

移除模块后，系统将按自身的 Device Owner 策略处理分身限制。

## 构建

需要 Python 3.10+、JDK 21、Android SDK Platform 35 和 Build Tools 35.0.0。

```sh
python scripts/build.py --sdk /path/to/android-sdk --jdk /path/to/jdk-21 --build-dir /path/to/build-cache
```

也可设置 `ANDROID_HOME` / `ANDROID_SDK_ROOT` 和 `JAVA_HOME`。构建中间文件保存在系统临时目录，支持用 `--build-dir` 指定；最终 APK、源码包及校验文件写入忽略的 `dist/`，可用 `--output-dir` 更改。

Xposed API 82 从官方仓库下载到构建缓存，并核对固定 SHA-256。离线构建可通过 `--xposed-api /path/to/api-82.jar` 提供相同文件。API 仅参与编译，运行时由 LSPosed 提供。

默认签名使用 `~/.android/debug.keystore`，也可通过 `--keystore` 指定。密码读取 `CLONEPROFILE_STORE_PASSWORD` 和 `CLONEPROFILE_KEY_PASSWORD` 环境变量，默认均为 Android 调试密钥的标准值 `android`。新环境可先创建自己的调试密钥：

```sh
keytool -genkeypair -keystore "$HOME/.android/debug.keystore" -storepass android -keypass android -alias androiddebugkey -dname "CN=Android Debug,O=Android,C=US" -keyalg RSA -keysize 2048 -validity 10000
```

签名私钥不随源码分发。自行构建的 APK 要覆盖已有安装，需要使用相同签名。

Windows 也可以使用 `build.ps1`，其参数包括 `-Sdk`、`-Jdk`、`-BuildDir`、`-OutputDir` 和 `-KeyStore`。

## 许可证与来源

本项目采用 Apache-2.0，原兼容模块来自 AxuanMDM 项目。第三方依赖及授权说明见 `NOTICE`、`licenses/` 和 `third_party/xposed-api/`。

[Xposed API 文档](https://api.xposed.info/) · [Android 16 DevicePolicyManagerService](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java)
