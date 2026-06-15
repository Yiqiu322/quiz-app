[app]
title = 刷题工具
package.name = quizzapp
package.domain = org.local
source.dir = .
source.main = mobile_app.py
source.include_exts = py,png,jpg,kv,db
version = 1.0
requirements = python3,kivy
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.3.1
fullscreen = 1
android.api = 34
android.minapi = 24
android.gradle_dependencies =
android.wakelock = False
android.arch = arm64-v8a
android.ndk = 27
android.sdk = 34
android.entitlements =

[buildozer]
log_level = 2
warn_on_root = 1
