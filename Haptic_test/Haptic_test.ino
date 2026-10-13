#include <Sparkfun_DRV2605L.h> //SparkFun Haptic Motor Driver Library 
#include <Wire.h> //I2C library 

SFE_HMD_DRV2605L HMD; //Create haptic motor driver object 

void setup() 
{
  Serial.begin(9600);
  Serial.println("Hello");
  HMD.begin();

  HMD.Mode(7); // Auto Calibration Mode
  
  
  HMD.MotorSelect(0xCA); // (0x36) ERM motor, 4x Braking, Medium loop gain, 1.365x back EMF gain; (0xC6) MSB LRA select bit so must pull high, 4x Braking, Medium Loop gain, 15x BEMF Gain
  HMD.ratevolt(75); // Rated Voltage
  HMD.clamp(87); // Overdrive clamp voltage value
  HMD.cntrl1(0x90); //Setting DRIVE_TIME. Keep default Control1 [7:5] as 0b100 (bit 6 is reserved so I set it to zero iguess), set [4:0] to 0b10000. Total reg should be 0b10010000 => 0x90
  HMD.go();
  delay(5000);
  if((HMD.readDRV2605L(0x00) & 0x08) > 0){
    Serial.println("Read Diag Bit bad");
  }else{
    Serial.println("Read Diag Bit good");
  }

  HMD.Mode(0); // Internal trigger input mode -- Must use the GO() function to trigger playback.
  HMD.Library(6); //1-5 & 7 for ERM motors, 6 for LRA motors 

}
void loop() 
{
  int seq = 0; //There are 8 sequence registers that can queue up to 8 waveforms
  for(int wave = 1; wave <=123; wave++) //There are 123 waveform effects 
  {
     HMD.Waveform(seq, wave);
     HMD.go();
     delay(3000); //give enough time to play effect 
     Serial.print("Waveform Sequence:      ");
     Serial.println(seq);
     Serial.print("Effect No.:      ");
     Serial.println(wave);

    if (wave%8==0) //Each Waveform register can queue 8 effects
    {
        seq=seq+1;
    }
    if (wave%64==0) // After the last register is used start over 
    {
        seq=0;
    }
  }
 }


