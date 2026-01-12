import subprocess

# Inicia o processo em segundo plano
# bufsize=1 significa que o Python vai ler linha por linha (sem esperar encher um buffer gigante)
processo = subprocess.Popen(
    ["adb", "shell", "getevent"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1 
)

print("--- Iniciando escuta do ADB (Pressione Ctrl+C para parar) ---")

try:
    # Loop infinito para ler enquanto o processo estiver vivo
    while True:
        # Lê a próxima linha disponível
        linha = processo.stdout.readline()
        
        # Se a linha vier vazia e o processo tiver morrido, paramos o loop
        if not linha and processo.poll() is not None:
            break

        if linha:
            linha = linha.strip() # Remove espaços extras e quebras de linha
            
            # --- SUA LÓGICA AQUI ---
            # O output do getevent geralmente é: "/dev/input/eventX: TIPO CODIGO VALOR"
            
            # Exemplo 1: Apenas imprimir tudo que chega
            # print(f"Recebido: {linha}")

            # Exemplo 2: Filtrar apenas o evento de toque (geralmente event3 ou event4 dependendo do celular)
            if "/dev/input/event3" in linha:
                
                # Vamos quebrar a linha nos espaços para pegar os códigos Hexadecimais
                partes = linha.split()
                # partes[0] -> dispositivo (/dev/input/event3:)
                # partes[1] -> tipo (ex: 0003)
                # partes[2] -> código (ex: 0035 para X ou 0036 para Y)
                # partes[3] -> valor (coordenada em hex)
                
                tipo = partes[1]
                codigo = partes[2]
                valor = partes[3]

                # Exemplo: Detectar coordenada X (0035 é comum para ABS_MT_POSITION_X)
                if codigo == "0035":
                    valor_decimal = int(valor, 16) # Converte Hex para Inteiro
                    print(f"Movimento no Eixo X detectado! Valor: {valor_decimal}")
                
                # Exemplo: Detectar "Touch Up" (dedo levantou)
                # O código específico varia, mas BTN_TOUCH UP costuma ter valor 00000000 num tipo EV_KEY (0001)
                elif tipo == "0001" and valor == "00000000":
                    print("--> O dedo foi levantado da tela!")

except KeyboardInterrupt:
    # Garante que o processo ADB seja morto se você parar o script com Ctrl+C
    print("\nParando o listener...")
    processo.terminate()