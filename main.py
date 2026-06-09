import sys
import os
import time
import base64
import math
import cv2
import qrcode

# Configuration Constants
CHUNK_SIZE = 300  # Number of raw bytes per QR code (keep small for low-density QR codes)
DELAY = 0.2       # Delay in seconds between frames on the sender side
HEADER_DELIMITER = "|"

def sender(file_path):
    if not os.path.exists(file_path):
        print(f"[-] Error: File '{file_path}' not found.")
        return

    file_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Calculate chunks
    total_chunks = math.ceil(len(file_bytes) / CHUNK_SIZE)
    print(f"[+] File size: {len(file_bytes)} bytes")
    print(f"[+] Total QR codes to transmit: {total_chunks}")
    print("[+] Initializing transmission. Press 'q' in the window to abort.")

    cv2.namedWindow("Sender - Scan with Receiver", cv2.WINDOW_NORMAL)

    # First, send a metadata chunk (seq = 0) containing filename and total chunks
    # Structure: 0|total_chunks|filename
    metadata = f"0{HEADER_DELIMITER}{total_chunks}{HEADER_DELIMITER}{file_name}"
    
    # Generate all QR frames beforehand for smooth playback
    frames = []
    
    # Metadata frame
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(metadata)
    qr.make(fit=True)
    frames.append(cv2.cvtColor(str(qr.make_image().convert('RGB')), cv2.COLOR_RGB2BGR))
    
    # Data frames (seq numbers 1 to total_chunks)
    for i in range(total_chunks):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(file_bytes))
        chunk_data = file_bytes[start:end]
        
        # Base64 encode the binary data to make it safe for string transport
        b64_data = base64.b64encode(chunk_data).decode('utf-8')
        
        # Structure: seq_num|total_chunks|payload
        payload = f"{i+1}{HEADER_DELIMITER}{total_chunks}{HEADER_DELIMITER}{b64_data}"
        
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image().convert('RGB')
        import numpy as np
        opencv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        frames.append(opencv_img)

    # Loop and display the frames sequentially
    idx = 0
    while True:
        cv2.imshow("Sender - Scan with Receiver", frames[idx])
        
        # Calculate visual pacing
        if idx == 0:
            # Give the receiver longer to lock onto the metadata frame initially
            key = cv2.waitKey(1500) & 0xFF
        else:
            key = cv2.waitKey(int(DELAY * 1000)) & 0xFF

        if key == ord('q'):
            break
            
        idx = (idx + 1) % len(frames)

    cv2.destroyAllWindows()
    print("[+] Transmission stopped.")

def receiver():
    # Initialize the OpenCV QR code detector
    detector = cv2.QRCodeDetector()
    
    # Initialize webcam (0 is typically the default built-in camera)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[-] Error: Could not open webcam.")
        return

    print("[+] Webcam initialized. Point it at the Sender screen.")
    
    metadata_received = False
    file_name = "received_file"
    total_chunks = 0
    chunks_dict = {}
    
    cv2.namedWindow("Receiver View", cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[-] Failed to grab frame.")
            break

        # Detect and decode QR code
        data, points, _ = detector.detectAndDecode(frame)
        
        if data:
            try:
                parts = data.split(HEADER_DELIMITER, 2)
                if len(parts) == 3:
                    seq_num = int(parts[0])
                    t_chunks = int(parts[1])
                    payload = parts[2]
                    
                    if seq_num == 0 and not metadata_received:
                        total_chunks = t_chunks
                        file_name = payload
                        metadata_received = True
                        print(f"[+] Metadata Detected! File: {file_name} | Total Chunks: {total_chunks}")
                    
                    elif seq_num > 0 and seq_num not in chunks_dict:
                        chunks_dict[seq_num] = payload
                        print(f"[+] Received Chunk {seq_num}/{total_chunks} "
                              f"({len(chunks_dict)}/{total_chunks} unique chunks collected)")
            except Exception as e:
                pass  # Ignore bad reads or temporary parsing issues due to camera blur

        # Overlay progress on camera frame
        status_text = f"Chunks: {len(chunks_dict)}/{total_chunks if total_chunks else '?'}"
        cv2.putText(frame, status_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        cv2.imshow("Receiver View", frame)
        
        # Check if all chunks are assembled
        if total_chunks > 0 and len(chunks_dict) == total_chunks:
            print("[+] All chunks successfully received! Reassembling file...")
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[-] Capture aborted by user.")
            cap.release()
            cv2.destroyAllWindows()
            return

    # Clean up tracking windows
    cap.release()
    cv2.destroyAllWindows()

    # Reassemble and write file
    try:
        file_bytes = bytearray()
        for i in range(1, total_chunks + 1):
            b64_payload = chunks_dict[i]
            file_bytes.extend(base64.b64decode(b64_payload))
        
        # Save to a distinct filename to prevent over-writing if in same directory
        output_name = "transferred_" + file_name
        with open(output_name, "wb") as f:
            f.write(file_bytes)
        print(f"[+] Success! File saved to disk as: {output_name}")
        
    except Exception as e:
        print(f"[-] Error reassembling file data: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  To Send:     python qr_transfer.py send <path_to_file>")
        print("  To Receive:  python qr_transfer.py receive")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "send":
        if len(sys.argv) < 3:
            print("[-] Error: Please specify the path of the file to send.")
            sys.exit(1)
        sender(sys.argv[2])
    elif mode == "receive":
        receiver()
    else:
        print("[-] Unknown mode. Use 'send' or 'receive'.")