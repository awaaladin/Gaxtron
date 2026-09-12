# Keep kotlinx.serialization models
-keepattributes *Annotation*, InnerClasses
-keep class com.gaxtron.mobile.data.network.dto.** { *; }
-keepclassmembers class kotlinx.serialization.json.** { *; }
