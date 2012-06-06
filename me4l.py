# -*- encoding: UTF-8 -*-

"""
    Author:      Jarek Żok <jarek.zok@fwioo.pl>
    Version:     0.0.1
    Description: Interfejs graficzny platformy mobilnej robota MOBOT-MBv2-AVR
    Hardware:    MOBOT-MBv2-AVR
                 Opis platormy na stronie: http://mobot.pl/index.php?site=products&type=855&details=7998

    Fundacja Wolnego i Otwartego Oprogramowania: http://fwioo.pl
"""

__author__      = "Jarosław Żok"
__copyright__   = "2012 Fundacja Wolnego i Otwartego Oprogramowania"
__license__     = "GPL"
__version__     = "0.0.1"
__maintainer__  = "Jarosław Żok"
__email__       = "jarek.zok@fwioo.pl"
__status__      = "Production"

import sys, time

from PyQt4 import QtCore, QtGui

from me4lwindow import Ui_MainWindow
from devenum import RadioDongle

FORWARD_BASE = 0x4b
BACKWARD_BASE = 0x7d
TIMER_T = 40        #Czas między wysłaniem kolejnego zapytania do robota lub sekwencji sterującej
SHUTDOWN_T = 2000   #Jak długo trwa czas zanim komunikacja z robotem zostanie uznana za zerwaną (ms)
MOVETIME_T = 250    #Jak długo trwa sekwencja ruchu (ms)

def resetShutOffTimer(func):
    """
        Nie pozwala timeoutować timera contimer
        Dekorator resetu timera rozłączającego komunikację dla niektórych metod klasy komunikującej się z robotem.
        (nie chcemy utracić komunikacji podczas dłuższej sekwencji ruchu na przykład)
    """
    def decorator(self, *args, **kwargs):
        self.contimer.start(SHUTDOWN_T)
        return func(self, *args, **kwargs)

    return decorator


class Me4LWindow(QtGui.QMainWindow):
    """
        Klasa okna aplikacji. Otwiera interfejs użytkownika, łączy zdarzenia z metodami i realizuje ruch robota
        wysyłając do niego odpowiednią sekwencję.
    """
    def __init__(self, parent = None):
        super(Me4LWindow, self).__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        #Wywolywany co kazde TIMER_Tms zapisuje aktualna sekwencje bajtow do robota i odczytuje zwrocone wartosci
        self.timer = QtCore.QTimer()

        #Jezeli po SHUTDOWN_Tms nastapi wywolanie timeoutu tego timera, polaczenie zostanie zerwane, self.timer nie dopuszcza do timeoutu
        self.contimer = QtCore.QTimer()

        #Gdy nacisniety przycisk sterowania robotem, self.timer wysyla sekwencje ruchu do robota, uruchamia ten timer i dopoki jest uruchomiony
        #nie wysyla do robota sekwencji pobrania pomiarow
        self.movetimer = QtCore.QTimer()

        #Pobieramy dostepne porty szeregowe i dodajemy ich liste do ComboBox
        self.serials = RadioDongle()
        for port in self.serials:
            self.ui.port.addItem(port)

        if len(self.serials) == 0:
            QtGui.QMessageBox.critical(self, "Mobot Explorer 4 Linux",
            u"Nie znaleziono portu RS232.\nSprawdź czy umieściłeś prawidłowo MOBOT-RCR w porcie USB.Sprawdź także, czy twój użytkownik ma prawa do odczytu plików /dev/tty* lub czy twój użytkownik należy do grupy \"dialout\"",
            QtGui.QMessageBox.Ok | QtGui.QMessageBox.Default,
            QtGui.QMessageBox.NoButton)



        QtCore.QObject.connect(self.ui.port, QtCore.SIGNAL('activated(int)'), self.portselect)
        QtCore.QObject.connect(self.ui.connect, QtCore.SIGNAL('stateChanged(int)'), self.connecto)
        QtCore.QObject.connect(self.ui.speed, QtCore.SIGNAL('sliderMoved(int)'), self.setspeed)

        QtCore.QObject.connect(self.ui.moveUp, QtCore.SIGNAL('pressed()'), self.moveforward)
        QtCore.QObject.connect(self.ui.moveDown, QtCore.SIGNAL('pressed()'), self.movebackward)
        QtCore.QObject.connect(self.ui.moveLeft, QtCore.SIGNAL('pressed()'), self.moveleft)
        QtCore.QObject.connect(self.ui.moveRight, QtCore.SIGNAL('pressed()'), self.moveright)
        QtCore.QObject.connect(self.ui.stop, QtCore.SIGNAL('pressed()'), self.stop)

        QtCore.QObject.connect(self.timer, QtCore.SIGNAL('timeout()'), self.communicate)
        QtCore.QObject.connect(self.contimer, QtCore.SIGNAL('timeout()'), self.shutoff)
        QtCore.QObject.connect(self.movetimer, QtCore.SIGNAL('timeout()'), self.movestop)

        QtCore.QObject.connect(self.ui.radioChannel, QtCore.SIGNAL('activated(int)'), self.setRadioChannel)
        QtCore.QObject.connect(self.ui.power, QtCore.SIGNAL('sliderMoved(int)'), self.setRadioPower)
        QtCore.QObject.connect(self.ui.uartspeed, QtCore.SIGNAL('sliderMoved(int)'), self.setRadioSpeed)
        QtCore.QObject.connect(self.ui.sensitivity, QtCore.SIGNAL('sliderMoved(int)'), self.setRadioSensitivity)
        QtCore.QObject.connect(self.ui.bufferSize, QtCore.SIGNAL('sliderMoved(int)'), self.setRadioBuffer)

        self.sfactor = 0.75 #Współczynnik prędkości dla 1-100%
        self.speed = self.sfactor * self.ui.speed.value() #Aktualna prędkość
        self.timersequence = [0xfc, 0x0a, 0x64, 0x64] #Normalna sekwencja wysyłana do robota
        self.miter = 0  #Pomiary sonarów są wykonywane 3x i uśredniane - przechowuje iterację pomiaru
        self.sonars = [0,0,0]   #Wyliczone średnie wartości pomiarów z sonarów

    def shutoff(self):
        '''
            Wywolywana gdy self.contimer odliczy zalozony czas.
            Powoduje zatrzymanie wszystkich timerów, rozłacza komunikację z robotem.
        '''
        self.timer.stop()
        self.contimer.stop()
        self.ui.connect.setCheckState(0)
        self.ui.sonar1.setValue(0)
        self.ui.sonar2.setValue(0)
        self.ui.sonar3.setValue(0)
        self.ui.status.setText(u"Brak komunikacji")
        self.ui.status.setStyleSheet("background: rgb(200, 160, 160);");

    def movestop(self):
        '''
            Gdy wcisnieto przycisk sterowania robotem, ten timer przywraca po krotkim czasie normalna sekwencje
            pomiarow z czujnikow.
        '''
        self.movetimer.stop()
        self.timersequence = [0xfc, 0x0a, 0x64, 0x64]
        self.movemode = False


    def communicate(self):
        '''
            Wywoływana gdy timer odliczy zadany czas. Jeżeli jesteśmy aktualnie w trybie ruchu wysyła do robota
            sekwencję ruchu. Przy każdym odliczeniu pobiera z robota wartości sonarów i pozostałych czujnikow.
            Jeżeli robot wysłał prawidłową sekwencję, resetuje timer contimer odłączający komunikację z robotem.
        '''
        if self.ui.connect.isChecked():
            self.measure = self.serials.write(self.timersequence)

            #Jezeli otrzymalismy sensowna odpowiedz od robota czyli nie jest to zaklocenie
            if self.measure and len(self.measure) == 8 and (self.measure[0] == chr(0xfe)):
                self.ui.status.setText(u"Połączony")
                self.ui.status.setStyleSheet("background: rgb(160, 200, 160);");
                if (self.miter % 3) == 0:
                    self.miter = 0
                    self.ui.sonar3.setValue(255 - (self.sonars[0] / 3))
                    self.ui.sonar1.setValue(255 - (self.sonars[1] / 3))
                    self.ui.sonar2.setValue(255 - (self.sonars[2] / 3))
                    print "S1={0} S2={1} S3={2}".format( self.sonars[0] / 3, self.sonars[1] / 3, self.sonars[2] / 3)
                    for i in range(3):
                        self.sonars[i] = 0
                else:
                    for i in range(3):
                        self.sonars[i] += ord(self.measure[i+2])

                self.miter += 1

                self.contimer.start(SHUTDOWN_T) #Resetujemy zegar odlaczenia od robota

    def setspeed(self, value):
        self.speed = int(self.sfactor * value)

    def portselect(self, index):
        self.serials.close()
        self.serials.open(self.ui.port.currentText())
        if self.ui.connect.isChecked():
            self.ui.connect.setCheckState(0)

    def connecto(self, state):
        if state == 0:
            self.ui.sonar1.setValue(0)
            self.ui.sonar2.setValue(0)
            self.ui.sonar3.setValue(0)
            self.timer.stop()
            self.contimer.stop()
            self.serials.close()
            self.ui.status.setText(u"Rozłączony")
            self.ui.status.setStyleSheet("");
        elif state == 2:
            if self.serials.is_closed():
                self.serials.open(self.ui.port.currentText())
            self.timer.start(TIMER_T)
            self.contimer.start(SHUTDOWN_T)
            self.ui.radioChannel.setCurrentIndex(self.serials.channel)
            self.ui.power.setValue(7 - self.serials.power)
            self.ui.uartspeed.setValue(self.serials.speed)
            self.ui.sensitivity.setValue(3 - self.serials.sens)
            self.ui.bufferSize.setValue(self.serials.buffer)


    @resetShutOffTimer
    def moveforward(self):
        self.timersequence = [0xfc, 0x0a, FORWARD_BASE - self.speed, FORWARD_BASE - self.speed]
        self.movetimer.start(MOVETIME_T)

    @resetShutOffTimer
    def movebackward(self):
        self.timersequence = [0xfc, 0x0a, BACKWARD_BASE + self.speed, BACKWARD_BASE + self.speed]
        self.movetimer.start(MOVETIME_T)

    @resetShutOffTimer
    def moveright(self):
        self.timersequence = [0xfc, 0x0a, BACKWARD_BASE + self.speed, FORWARD_BASE - self.speed]
        self.movetimer.start(MOVETIME_T)

    @resetShutOffTimer
    def moveleft(self):
        self.timersequence = [0xfc, 0x0a, FORWARD_BASE - self.speed, BACKWARD_BASE + self.speed]
        self.movetimer.start(MOVETIME_T)

    @resetShutOffTimer
    def stop(self):
        self.timersequence = [0xfc, 0x00, 0x64, 0x64]
        self.movetimer.start(MOVETIME_T)

    def setRadioChannel(self, channel):
        self.serials.channel = channel
        self.ui.radioStatus.setText(self.serials.status)

    def setRadioPower(self, power):
        self.serials.power = power
        self.ui.radioStatus.setText(self.serials.status)

    def setRadioSpeed(self, speed):
        self.serials.speed = speed
        self.ui.radioStatus.setText(self.serials.status)

    def setRadioSensitivity(self, sens):
        self.serials.sens = sens
        self.ui.radioStatus.setText(self.serials.status)

    def setRadioBuffer(self, bytes):
        self.serials.buffer = bytes
        self.ui.radioStatus.setText(self.serials.status)



if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    appw = Me4LWindow()
    appw.show()
    sys.exit(app.exec_())
