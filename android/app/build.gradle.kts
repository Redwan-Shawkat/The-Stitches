import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Signing comes from android/keystore.properties when it exists (build-apk.sh
// creates one on first run), or from the environment on CI. Neither is in git.
val keystoreProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun signingValue(key: String, env: String): String? =
    keystoreProperties.getProperty(key) ?: System.getenv(env)

android {
    namespace = "io.github.redwanshawkat.uninstaller"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.redwanshawkat.uninstaller"
        minSdk = 24
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.0"
    }

    val storeFilePath = signingValue("storeFile", "ANDROID_KEYSTORE_FILE")
    if (storeFilePath != null) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(storeFilePath)
                storePassword = signingValue("storePassword", "ANDROID_KEYSTORE_PASSWORD")
                keyAlias = signingValue("keyAlias", "ANDROID_KEY_ALIAS")
                keyPassword = signingValue("keyPassword", "ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin {
        compilerOptions.jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }

    testOptions.unitTests.isReturnDefaultValues = true
}

// No AndroidX, no Material components, no Compose: the app draws with the
// platform's own android.widget toolkit. See documents/ai-knowledgebase.md.
dependencies {
    testImplementation("junit:junit:4.13.2")
}
