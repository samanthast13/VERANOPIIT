const int pinSI = 3;
const int pinCLK = 2;
const int pinAO = A0;

int pixelData[128];
unsigned long exposureTime = 50;

void setup() {
  pinMode(pinSI, OUTPUT);
  pinMode(pinCLK, OUTPUT);
  pinMode(pinAO, INPUT);

  digitalWrite(pinSI, LOW);
  digitalWrite(pinCLK, LOW);

  Serial.begin(115200);
}

void leerCamara() {
  digitalWrite(pinCLK, LOW);
  digitalWrite(pinSI, HIGH);
  digitalWrite(pinCLK, HIGH);
  digitalWrite(pinSI, LOW);

  pixelData[0] = analogRead(pinAO);

  for (int i = 1; i < 128; i++) {
    digitalWrite(pinCLK, LOW);
    digitalWrite(pinCLK, HIGH);
    pixelData[i] = analogRead(pinAO);
  }

  digitalWrite(pinCLK, LOW);
}

void enviarDatos() {
  for (int i = 0; i < 128; i++) {
    Serial.print(pixelData[i]);
    if (i < 127) Serial.print(",");
  }
  Serial.println();
}

void revisarComandos() {
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    entrada.trim();
    if (entrada.length() > 0) {
      long valor = entrada.toInt();
      if (valor > 0) {
        exposureTime = valor;
      }
    }
  }
}

void loop() {
  revisarComandos();
  leerCamara();
  enviarDatos();
  delay(exposureTime);
}
