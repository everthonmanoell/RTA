# RTA Android App

## Configuração Inicial

### Pré-requisitos
- Android Studio instalado
- Android SDK instalado
- Java Development Kit (JDK) 11 ou superior (certifique-se de que a variável de ambiente `JAVA_HOME` está apontando para o seu JDK).

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
   # No Windows (PowerShell), se precisar configurar o JAVA_HOME temporariamente:
   # $env:JAVA_HOME="C:\Program Files\Android\Android Studio\jbr"
   
   ./gradlew installDebug
   ```

## Uso

### Iniciando o aplicativo (via ADB)
O aplicativo foi reestruturado e dividido em múltiplas *Activities* independentes para facilitar o rastreamento via automação. A primeira tela a ser chamada deve ser sempre a `InitialActivity`.

* Celular normal (4 markers):
  ```bash
  adb shell am start -n com.example.rta/.InitialActivity --es device_type flat
  ```
* Celular dobrável (8 markers):
  ```bash
  adb shell am start -n com.example.rta/.InitialActivity --es device_type foldable
  ```

### Verificando a Tela Atual (Automação / ADB)
Como cada tela do aplicativo agora possui sua própria `Activity`, você pode descobrir facilmente em qual etapa o aplicativo se encontra inspecionando qual Activity está em primeiro plano (focus):

```bash
# No Windows
adb shell dumpsys window windows | findstr mCurrentFocus

# No Linux / Mac
adb shell dumpsys window windows | grep mCurrentFocus
```

O comando retornará a Activity em foco. O fluxo atual de Activities é:
1. `InitialActivity`: Tela inicial com um grande marcador Aruco ao centro.
2. `IntermediateActivity`: Tela branca com um botão vermelho (10x10px) invisível ao centro.
3. `ArucoMarkersActivity`: Tela com os 4 ou 8 marcadores ArUco nas bordas do aparelho.
4. `GridActivity`: Tela interativa de grade para mapear toques na tela (validação).
5. `SuccessActivity`: Tela verde de sucesso (exibe ArUco tag 14).
6. `FailureActivity`: Tela vermelha de falha na validação (exibe ArUco tag 15).
7. `QrCodeActivity`: Tela com o QR Code exibindo os metadados do display do aparelho.