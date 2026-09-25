[app]

# (str) Title of your application
title = Daily Quest Tracker

# (str) Package name / domain (together they form the Android package id)
package.name = dailyquesttracker
package.domain = org.dailyquest

# (str) Source code where main.py lives
source.dir = daily_quest_tracker

# (list) File extensions to include in the APK
source.include_exts = py,png,jpg,kv,atlas,json,ttf,txt

# (list) Directories to leave out of the APK
source.exclude_dirs = tests,__pycache__,.pytest_cache

# (str) Application version
version = 0.1.0

# (list) Python-for-android recipes / pip packages.
# sqlite3 and openssl are needed for the standard-library sqlite3 and ssl modules.
requirements = python3,kivy==2.3.1,sqlite3,openssl,certifi,filetype

# (str) Presplash and icon
presplash.filename = %(source.dir)s/assets/images/presplash.png
icon.filename = %(source.dir)s/assets/images/icon.png
android.presplash_color = #1C1814

# (list) Supported orientations
orientation = portrait

# (bool) Fullscreen (hides the status bar)
fullscreen = 0

#
# Android specific
#

# INTERNET is only used for the optional weather lookup; the app works offline.
android.permissions = INTERNET

android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a

# (bool) Automatically accept the SDK license during the first build
android.accept_sdk_license = True

# (bool) Allow backup of the app data (the SQLite save file) via Android backup
android.allow_backup = True

# (str) Format used to package the app for release (aab for Play Store, apk for sideloading)
android.release_artifact = aab
android.debug_artifact = apk

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
