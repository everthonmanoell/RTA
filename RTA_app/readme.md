# RTA Android App

## Configuração Inicial

### Pré-requisitos
- Android Studio instalado
- Android SDK instalado
- Java Development Kit (JDK) 11 ou superior

### Primeiro Setup na Máquina

1. **Configurar Android SDK:**
   - Instale o Android Studio que incluirá o Android SDK
   - Ou instale apenas o Android SDK Command Line Tools

2. **Configurar o projeto:**
   ```bash
   cd RTA_app
   cp local.properties.example local.properties
   ```

3. **Editar `local.properties`** e configurar o caminho do SDK:
   - **Linux/Mac:** `sdk.dir=/home/seu_usuario/Android/Sdk`
   - **Windows:** `sdk.dir=C\:\\Users\\seu_usuario\\AppData\\Local\\Android\\Sdk`
   
   **OU** configurar a variável de ambiente:
   ```bash
   export ANDROID_HOME=/path/to/your/android/sdk
   ```

4. **Instalar a aplicação:**
   ```bash
   ./gradlew installDebug
   ```

## Uso

### Chamadas de tipos de celular por quantidade de aruco
* Celular normal (4 markers):
  * ```adb shell am start -n com.example.rta/.MainActivity --es device_type flat```
  * * Celular dobravel (8 markers):
  * ```adb shell am start -n com.example.rta/.MainActivity --es device_type foldable```