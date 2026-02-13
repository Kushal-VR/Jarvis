import time

print("Starting sustained disk write simulation...")

for i in range(100):
    with open("sustained_test.bin", "ab") as f:
        f.write(b"A" * 1_000_000)  # 1 MB

    print(f"Write cycle {i}")
    time.sleep(0.3)  # slower, easier to detect

print("Finished.")
