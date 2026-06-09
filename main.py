import sys
import os
import base64
import math
import cv2
import qrcode
import numpy as np

CHUNK_SIZE = 300  
HEADER_DELIMITER = "|"

def create_qr_image(data):
    """Helper function to generate an OpenCV-compatible image from a string."""
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image().convert('RGB')
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def sender(file_path):
    if not os.path.exists(file_path):
        print(f"[-] Error: File '{file_path}' not found.")
        return

    file_name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    total_chunks = math.ceil(len(file_bytes) / CHUNK_SIZE)
    print(f"File size: {len(file_bytes)} bytes")
    print(f"Total chunks to transmit: {total_chunks}")
    print("Initializing Two-Way Transmission. Press 'q' to abort.")

    # Protocol Format -> D|seq_num|total_chunks|payload
    frames = []
    
    # Seq 0: Metadata
    metadata = f"D{HEADER_DELIMITER}0{HEADER_DELIMITER}{total_chunks}{HEADER_DELIMITER}{file_name}"
    frames.append(create_qr_image(metadata))
    
    # Seq 1..N: Data Chunks
    for i in range(total_chunks):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(file_bytes))
        b64_data = base64.b64encode(file_bytes[start:end]).decode('utf-8')
        
        payload = f"D{HEADER_DELIMITER}{i+1}{HEADER_DELIMITER}{total_chunks}{HEADER_DELIMITER}{b64_data}"
        frames.append(create_qr_image(payload))

    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()
    current_seq = 0

    cv2.namedWindow("Sender - SHOW THIS TO RECEIVER", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Sender Camera", cv2.WINDOW_NORMAL)

    while current_seq <= total_chunks:
        cv2.imshow("Sender - SHOW THIS TO RECEIVER", frames[current_seq])

        ret, frame = cap.read()
        if not ret:
            print("Webcam failed.")
            break

        cv2.imshow("Sender Camera", frame)

        data, _, _ = detector.detectAndDecode(frame)
        
        # Protocol Format -> A|seq_num
        if data and data.startswith("A" + HEADER_DELIMITER):
            try:
                ack_seq = int(data.split(HEADER_DELIMITER)[1])
                if ack_seq == current_seq:
                    print(f"Received ACK for chunk {current_seq}. Moving to next.")
                    current_seq += 1
            except Exception:
                pass # Ignore malformed QR reads

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Aborted by user.")
            break

    if current_seq > total_chunks:
        print("All chunks successfully acknowledged! Transmission complete.")

    cap.release()
    cv2.destroyAllWindows()


def receiver():
    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()
    
    expected_seq = 0
    total_chunks = 0
    file_name = "received_file"
    chunks_dict = {}
    
    ack_img = None # Will hold the QR image for the ACK we need to display
    
    print("Waiting for sender... Press 'q' to abort.")
    
    cv2.namedWindow("Receiver Camera", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Receiver - SHOW THIS TO SENDER", cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Scan for incoming Data chunks
        data, _, _ = detector.detectAndDecode(frame)
        
        if data and data.startswith("D" + HEADER_DELIMITER):
            try:
                parts = data.split(HEADER_DELIMITER, 3)
                seq_num = int(parts[1])
                t_chunks = int(parts[2])
                payload = parts[3]
                
                if seq_num == expected_seq:
                    if seq_num == 0:
                        file_name = payload
                        total_chunks = t_chunks
                        print(f"Metadata received. File: {file_name}")
                    else:
                        chunks_dict[seq_num] = payload
                        print(f"Received Chunk {seq_num}/{total_chunks}")
                    
                    ack_img = create_qr_image(f"A{HEADER_DELIMITER}{seq_num}")
                    expected_seq += 1

                elif seq_num < expected_seq:
                    ack_img = create_qr_image(f"A{HEADER_DELIMITER}{seq_num}")

            except Exception:
                pass

        cv2.imshow("Receiver Camera", frame)
        
        if ack_img is not None:
            cv2.imshow("Receiver - SHOW THIS TO SENDER", ack_img)

        if total_chunks > 0 and expected_seq > total_chunks:
            print("All data received! Sending final ACK buffer...")
            cv2.waitKey(2000) 
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    # Reassemble file
    if total_chunks > 0 and len(chunks_dict) == total_chunks:
        try:
            file_bytes = bytearray()
            for i in range(1, total_chunks + 1):
                b64_payload = chunks_dict[i]
                file_bytes.extend(base64.b64decode(b64_payload))
            
            output_name = "transferred_" + file_name
            with open(output_name, "wb") as f:
                f.write(file_bytes)
            print(f"Success! File saved to disk as: {output_name}")
            
        except Exception as e:
            print(f"Error reassembling file data: {e}")
    else:
        print("Transfer incomplete. No file saved.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  To Send:     python main.py send <path_to_file>")
        print("  To Receive:  python main.py receive")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "send":
        if len(sys.argv) < 3:
            print("Error: Please specify the path of the file to send.")
            sys.exit(1)
        sender(sys.argv[2])
    elif mode == "receive":
        receiver()
    else:
        print("Unknown mode. Use 'send' or 'receive'.")