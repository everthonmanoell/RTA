### Chamadas de tipos de celular por quantidade de aruco
* Celular normal (4 markers):
  * ```adb shell am start -n com.example.rta/.MainActivity --es device_type flat```
  * * Celular dobravel (8 markers):
  * ```adb shell am start -n com.example.rta/.MainActivity --es device_type foldable```