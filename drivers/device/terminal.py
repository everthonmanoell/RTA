import subprocess

# Start the process in the background
# bufsize=1 means Python will read line by line (without waiting for a huge buffer to fill)
processo = subprocess.Popen(
    ["adb", "shell", "getevent"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

print("--- Starting ADB listening (Press Ctrl+C to stop) ---")

try:
    # Infinite loop to read while the process is alive
    while True:
        # Read the next available line
        linha = processo.stdout.readline()

        # If the line is empty and the process has exited, stop the loop
        if not linha and processo.poll() is not None:
            break

        if linha:
            linha = linha.strip()  # Remove extra spaces and line breaks

            # --- YOUR LOGIC HERE ---
            # getevent output is usually: "/dev/input/eventX: TYPE CODE VALUE"

            # Example 1: Just print everything that arrives
            # print(f"Received: {linha}")

            # Example 2: Filter only touch events (usually event3 or event4 depending on the phone)
            if "/dev/input/event3" in linha:

                # Split the line by spaces to extract the hexadecimal codes
                partes = linha.split()
                # partes[0] -> device (/dev/input/event3:)
                # partes[1] -> type (e.g. 0003)
                # partes[2] -> code (e.g. 0035 for X or 0036 for Y)
                # partes[3] -> value (coordinate in hex)

                tipo = partes[1]
                codigo = partes[2]
                valor = partes[3]

                # Example: Detect X coordinate (0035 is common for ABS_MT_POSITION_X)
                if codigo == "0035":
                    valor_decimal = int(valor, 16)  # Convert hex to integer
                    print(f"X-axis movement detected! Value: {valor_decimal}")

                # Example: Detect "Touch Up" (finger lifted)
                # The exact code varies, but BTN_TOUCH UP usually has value 00000000 in an EV_KEY (0001) event
                elif tipo == "0001" and valor == "00000000":
                    print("--> The finger was lifted from the screen!")

except KeyboardInterrupt:
    # Ensure the ADB process is terminated if you stop the script with Ctrl+C
    print("\nStopping the listener...")
    processo.terminate()
