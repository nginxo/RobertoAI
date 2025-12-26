import pyaudio
import json
import socket
import threading
import time
import sys
from vosk import Model, KaldiRecognizer

# ================= CONFIG =================
WAKE_WORD = "roberto"
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 65432
MIC_DEVICE_INDEX = 0
MODEL_PATH = "./"  # vosk-model-small-it-0.22
SAMPLE_RATE = 16000

# ================= PROTOCOL =================
# Messaggi inviati al main:
# - WAKE_DETECTED: wake word rilevata
# - COMMAND:<testo>: comando vocale riconosciuto
# - LISTENING_START: iniziato ascolto comando
# - LISTENING_TIMEOUT: timeout ascolto comando
# - ERROR:<messaggio>: errore

# Messaggi ricevuti dal main:
# - START_LISTENING: inizia ad ascoltare un comando
# - STOP_LISTENING: ferma l'ascolto del comando
# - INTERRUPT: interrompi tutto

# ================= WAKE WORD DETECTOR =================
class VoiceService:
    def __init__(self):
        self.running = False
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.pa = None
        self.socket_client = None
        
        # Stati
        self.listening_mode = "wake"  # "wake" o "command"
        self.last_detection_time = 0
        self.detection_cooldown = 1.0
        self.command_start_time = 0
        self.command_timeout = 15  # secondi
        self.command_buffer = []
        
    def initialize(self):
        """Inizializza Vosk e PyAudio"""
        try:
            print("📦 Caricamento modello Vosk...")
            self.model = Model(MODEL_PATH)
            self.recognizer = KaldiRecognizer(self.model, SAMPLE_RATE)
            self.recognizer.SetWords(True)
            
            print("🎤 Inizializzazione microfono...")
            self.pa = pyaudio.PyAudio()
            self.audio_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=4000,
                input_device_index=MIC_DEVICE_INDEX
            )
            
            print(f"✅ Voice service inizializzato (wake word: '{WAKE_WORD}')")
            return True
            
        except Exception as e:
            print(f"❌ Errore inizializzazione: {e}")
            return False
    
    def connect_to_main(self):
        """Connetti al servizio main.pyw"""
        max_retries = 20
        retry_count = 0
        
        while retry_count < max_retries and self.running:
            try:
                self.socket_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket_client.connect((SOCKET_HOST, SOCKET_PORT))
                self.socket_client.settimeout(0.1)  # Non-blocking per ricevere comandi
                print(f"✅ Connesso a main.pyw su {SOCKET_HOST}:{SOCKET_PORT}")
                return True
            except Exception as e:
                retry_count += 1
                print(f"⏳ Tentativo {retry_count}/{max_retries} - In attesa di main.pyw...")
                time.sleep(2)
        
        print("❌ Impossibile connettersi a main.pyw")
        return False
    
    def send_message(self, message):
        """Invia messaggio a main.pyw"""
        try:
            if self.socket_client:
                self.socket_client.sendall(message.encode('utf-8'))
                return True
        except Exception as e:
            print(f"❌ Errore invio messaggio: {e}")
            # Prova a riconnettersi
            try:
                self.socket_client.close()
            except:
                pass
            return self.connect_to_main()
        return False
    
    def receive_commands(self):
        """Thread che riceve comandi dal main"""
        while self.running:
            try:
                if self.socket_client:
                    try:
                        data = self.socket_client.recv(1024)
                        if data:
                            command = data.decode('utf-8').strip()
                            self.handle_command(command)
                    except socket.timeout:
                        pass
                    except Exception as e:
                        if self.running:
                            print(f"⚠️ Connessione persa: {e}")
                            time.sleep(1)
                            self.connect_to_main()
            except Exception as e:
                if self.running:
                    print(f"❌ Errore ricezione comandi: {e}")
            time.sleep(0.1)
    
    def handle_command(self, command):
        """Gestisce comandi ricevuti dal main"""
        print(f"📨 Comando ricevuto: {command}")
        
        if command == "START_LISTENING":
            self.start_command_listening()
        elif command == "STOP_LISTENING":
            self.stop_command_listening()
        elif command == "INTERRUPT":
            self.interrupt()
    
    def start_command_listening(self):
        """Inizia modalità ascolto comando"""
        print("🎯 Modalità COMANDO attivata")
        self.listening_mode = "command"
        self.command_start_time = time.time()
        self.command_buffer = []
        self.recognizer.Reset()  # Reset del recognizer per nuovo comando
        self.send_message("LISTENING_START")
    
    def stop_command_listening(self):
        """Ferma modalità ascolto comando"""
        print("🛑 Modalità COMANDO disattivata")
        self.listening_mode = "wake"
        self.command_buffer = []
        self.recognizer.Reset()
    
    def interrupt(self):
        """Interrompi tutto e torna in modalità wake"""
        print("⚠️ INTERRUPT ricevuto")
        self.stop_command_listening()
    
    def check_wake_word(self, text):
        """Controlla se il testo contiene la wake word"""
        text_lower = text.lower()
        words = text_lower.split()
        
        # Controlla presenza esatta
        if WAKE_WORD in words:
            return True
        
        # Varianti comuni per compensare errori
        variants = ["roberto", "roberta", "rubberto", "roberto"]
        for variant in variants:
            if variant in text_lower:
                return True
        
        return False
    
    def process_wake_mode(self, text):
        """Processa testo in modalità wake word"""
        if self.check_wake_word(text):
            current_time = time.time()
            if current_time - self.last_detection_time > self.detection_cooldown:
                print(f"🎯 Wake word '{WAKE_WORD}' rilevata!")
                self.send_message("WAKE_DETECTED")
                self.last_detection_time = current_time
    
    def process_command_mode(self, text, is_final=True):
        """Processa testo in modalità comando"""
        if not text:
            return
        
        # Aggiungi al buffer
        if is_final:
            self.command_buffer.append(text)
            print(f"📝 Comando parziale: '{text}'")
        
        # Check timeout
        if time.time() - self.command_start_time > self.command_timeout:
            print("⏱️ Timeout ascolto comando")
            
            # Invia comando completo se c'è qualcosa
            if self.command_buffer:
                full_command = " ".join(self.command_buffer)
                print(f"✅ Comando completo: '{full_command}'")
                self.send_message(f"COMMAND:{full_command}")
            else:
                self.send_message("LISTENING_TIMEOUT")
            
            self.stop_command_listening()
            return
        
        # Invia comando dopo una pausa (1.5 secondi di silenzio)
        # Questo viene gestito dal riconoscitore finale
        if is_final and self.command_buffer:
            # Attendi un po' per vedere se c'è altro
            time.sleep(0.3)
    
    def listen(self):
        """Loop principale di ascolto"""
        print("👂 In ascolto...")
        print(f"💬 Pronuncia '{WAKE_WORD}' per attivare Roberto\n")
        
        silence_start = None
        command_sent = False
        
        while self.running:
            try:
                # Leggi audio
                data = self.audio_stream.read(4000, exception_on_overflow=False)
                
                if self.recognizer.AcceptWaveform(data):
                    # Risultato finale (frase completa)
                    result = json.loads(self.recognizer.Result())
                    text = result.get('text', '').strip()
                    
                    if text:
                        print(f"🎤 Rilevato: '{text}'")
                        
                        if self.listening_mode == "wake":
                            self.process_wake_mode(text)
                        elif self.listening_mode == "command":
                            self.process_command_mode(text, is_final=True)
                            silence_start = time.time()
                            command_sent = False
                    
                else:
                    # Risultato parziale
                    partial = json.loads(self.recognizer.PartialResult())
                    partial_text = partial.get('partial', '').strip()
                    
                    if self.listening_mode == "command":
                        # Mostra progresso
                        if partial_text:
                            sys.stdout.write(f"\r💭 {partial_text}                    ")
                            sys.stdout.flush()
                            silence_start = None
                        else:
                            # Silenzio rilevato
                            if silence_start is None:
                                silence_start = time.time()
                            elif not command_sent and self.command_buffer:
                                # Dopo 1.5 secondi di silenzio, invia il comando
                                if time.time() - silence_start > 1.5:
                                    sys.stdout.write("\n")
                                    full_command = " ".join(self.command_buffer)
                                    print(f"✅ Comando completo: '{full_command}'")
                                    self.send_message(f"COMMAND:{full_command}")
                                    self.stop_command_listening()
                                    command_sent = True
                    
                    elif self.listening_mode == "wake" and partial_text and len(partial_text) > 3:
                        # Mostra solo se abbastanza lungo (modalità wake)
                        sys.stdout.write(f"\r💭 {partial_text}                    ")
                        sys.stdout.flush()
                    
            except Exception as e:
                print(f"\n❌ Errore durante ascolto: {e}")
                time.sleep(0.1)
    
    def start(self):
        """Avvia il servizio"""
        self.running = True
        
        if not self.initialize():
            return False
        
        if not self.connect_to_main():
            return False
        
        # Avvia thread di ascolto
        listen_thread = threading.Thread(target=self.listen, daemon=True)
        listen_thread.start()
        
        # Avvia thread ricezione comandi
        receive_thread = threading.Thread(target=self.receive_commands, daemon=True)
        receive_thread.start()
        
        return True
    
    def stop(self):
        """Ferma il servizio"""
        print("\n🛑 Fermando servizio...")
        self.running = False
        
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        
        if self.pa:
            self.pa.terminate()
        
        if self.socket_client:
            try:
                self.socket_client.close()
            except:
                pass
        
        print("✅ Servizio fermato")

# ================= MAIN =================
def main():
    print("=" * 60)
    print("🎤 Servizio riconoscimento vocale per RobertoAI")
    print("=" * 60)
    
    service = VoiceService()
    
    if not service.start():
        print("\n❌ Impossibile avviare il servizio")
        return
    
    print("\n✅ Servizio attivo - Premi Ctrl+C per uscire\n")
    
    try:
        # Mantieni il programma attivo
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⚠️ Interruzione ricevuta...")
    finally:
        service.stop()

if __name__ == "__main__":
    main()