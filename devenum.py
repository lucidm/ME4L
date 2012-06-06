# -*- encoding: UTF-8 -*-

"""
    Author:      Jarek Żok <jarek.zok@fwioo.pl>
    Version:     0.0.1
    Description: Moduł obsługi portu szeregowego oraz dongla radio MOBOT-RCR-USB-V2
    Hardware:    MOBOT-RCR-USB-V2
                 Opis dongla na stronie: http://mobot.pl/index.php?site=products&type=853&details=7770

    Fundacja Wolnego i Otwartego Oprogramowania: http://fwioo.pl
"""

__author__      = "Jarosław Żok"
__copyright__   = "2012 Fundacja Wolnego i Otwartego Oprogramowania"
__license__     = "GPL"
__version__     = "0.0.1"
__maintainer__  = "Jarosław Żok"
__email__       = "jarek.zok@fwioo.pl"
__status__      = "Production"

import serial, glob, os, sys, struct, time, pprint

class SeException(Exception):
    """
        Wyjątek dla klasy SerialEnumerator.
        Aktualnie wykorzystywany gdy odwołano się do portu, który SerialEnumerator nie odnalazł
        na swojej liście aktywnych portów.
    """
    pass

class SerialEnumerator(object):
    """
        Klasa jest interfejsem dla portu szeregowego.
        Jako iterator zwraca w kolejnych iteracjach nazwy aktywnych w systemie
        portów szeregowych.
    """
    sout = {}
    port = None


    def __init__(self):
        self.sout = {}
        self.port = None

    def __packbyte(self, value):
        """
            Zamienia wartość int pythona na wartość char w C
        """
        return struct.pack('<B', value)

    def __unpackint(self, data):
        """
        """
        p = []
        for i in range(0,len(data), 2):
             p.append(struct.unpack('>h', data[i] + data[i+1]))

        return p

    def __iter__(self):
        if not self.sout:
            self.enum()
        return self.sout.iterkeys()

    def __len__(self):
        if not self.sout:
            self.enum()
        return len(self.sout)


    def printstr(self, data):
        """
            Wysyła ciąg znaków jako string do portu szeregowego.
        """
        self.port.flush()
        self.port.write(data)

    def write(self, data):
        """
            Wysyła ciąg wartości zapisanych jako lista w data do portu szeregowego.
        """
        r = []
        for c in data:
            r.append(self.__packbyte(c))
        s = "".join(r)

        try:
            #print "W:" + s.encode('hex')
            self.port.write(s)
            time.sleep(0.016)
            self.port.flush()

            b = self.port.inWaiting()
            #print b
            if b > 0:
                ret = self.port.read(size = b)
                #print "R:" + ret.encode('hex')
                #ret = self.__unpackint(ret)
                #pprint.pprint(ret)
                return ret
            else:
                ret = None
            return ret
        except serial.SerialException as e:
            raise SeException(u"Błąd zapisu do portu {0}".format(port))


    def open(self, port):
        """
            Otwiera jeden ze znalezionych aktywnych portów szeregowych.
            Nazwę portu podaje się jako argument do metody. Nazwy portów
            uzyskuje się przez iterację po instancji klasy.
        """
        if not self.sout:
            self.enum()

        port = str(port)
        if not self.sout.has_key(port):
            raise SeException(u"Nie znaleziono portu :{0}:".format(port))

        self.close()
        try:
            self.port = serial.Serial(self.sout[port], baudrate=56000, timeout=None)
        except serial.SerialException:
            raise SeException(u"Problem z otwarciem portu {0}".format(port))

    def close(self):
        """
            Zamyka wcześniej otwarty port szeregowy.
        """
        if self.port and self.port.isOpen():
            self.port.close()
            self.port = None

    def is_closed(self):
        return self.port is None

    def enum(self):
        """
            Metoda służy do zbierania aktywnych portów szeregowych.
            W przyszłości powinna zostać zmieniona aby używała udev
            zamiast naiwnego otwierania portów i przechwytywania wyjątków
            gdy port nie jest aktywny.
        """
        sers = glob.glob('/dev/ttyS*') + glob.glob('/dev/ttyUSB*')

        for port in sers:
            try:
                s = serial.Serial(port)
                s.open()
                if s.isOpen():
                    self.sout[os.path.basename(port)] = port
                    s.close()
            except serial.SerialException as e:
                pass


class RadioDongle(SerialEnumerator):
    """
        Klasa służy do komunikacji z donglem radiowym, który w systemie
        widoczny jest jako kolejny port szeregowy.
        Dokumentacja do dongla znajduje się na stronie:
        http://mobot.pl/index.php?site=products&type=853&details=7770
    """
    status = ''

    def __init__(self, port = None):
        super(SerialEnumerator,self).__init__()
        self.status = ''
        if port:
            self.open(port)

    def __getattribute__(self, attr):
        """
            Dostęp do ustawień dongla przez pięć wartości:
            channel - numer kanału od 0 do 9
            speed - szybkość komunikacji szeregowej od 1 do 56 (mnożone razy 1000 dając efektywnie 1000 do 56000 bps)
            power - moc radio nadajnika 0 - najmocniejsza do 7 - najsłabsza
            sens  - czułość radio odbiornika 0 największa do 3 - najmniejsza
            buffer - wielkość bufora nadawczo - odbiorczego, dane są wysyłane w eter paczkami, ta wartość określa
                     wielkość tej paczki
        """
        if attr == 'channel':
            r = self.write([0x43, 0x78, 0x1e, 0x07, 254])
        elif attr == 'speed':
            r = self.write([0x43, 0x78, 0x1e, 0x08, 254])
        elif attr == 'power':
            r = self.write([0x43, 0x78, 0x1e, 0x09, 254])
        elif attr == 'sens':
            r = self.write([0x43, 0x78, 0x1e, 0x10, 254])
        elif attr == 'buffer':
            r = self.write([0x43, 0x78, 0x1e, 0x11, 254])
        else:
            return object.__getattribute__(self, attr)
        return ord(r)

    def __setattr__(self, attr, value):
        """
            Zmiana ustawień odbywa się przez przypisanie wartości do atrybutów instancji, poniżej te atrybuty:
            channel - numer kanału od 0 do 9
            speed - szybkość komunikacji szeregowej od 1 do 56 (mnożone razy 1000 dając efektywnie 1000 do 56000 bps)
            power - moc radio nadajnika 0 - najmocniejsza do 7 - najsłabsza
            sens  - czułość radio odbiornika 0 największa do 3 - najmniejsza
            buffer - wielkość bufora nadawczo - odbiorczego, dane są wysyłane w eter paczkami, ta wartość określa
                     wielkość tej paczki
            Metoda dba przy okazji o poprawne wartości poszczególnych parametrów wyrzucając wyjątek gdy przekraczają
            one dozwolone wartości.

        """
        if attr == 'channel':
            if value not in range(0,10):
                raise AttributeError("Numer kanału poza przedziałem 0...9")
            self.status = self.write([0x43, 0x78, 0x1e, 0x07, value])
        elif attr == 'speed':
            if value not in range(1,57):
                raise AttributeError("Szybkość łącza poza przedziałem 1...56")
            self.status = self.write([0x43, 0x78, 0x1e, 0x08, value])
        elif attr == 'power':
            if value not in range(0,8):
                raise AttributeError("Moc nadajnika poza przedziałem 0...7")
            self.status = self.write([0x43, 0x78, 0x1e, 0x09, value])
        elif attr == 'sens':
            if value not in range(0,4):
                raise AttributeError("Czułość nadajnika poza przedziałem 0...3")
            self.status = self.write([0x43, 0x78, 0x1e, 0x10, value])
        elif attr == 'buffer':
            if value not in range(1, 129):
                raise AttributeError("Wielkość bufora poza przedziałem 0...128")
            self.status = self.write([0x43, 0x78, 0x1e, 0x11, value])
        else:
            object.__setattr__(self, attr, value)

    def __del__(self):
        self.close()

if __name__=='__main__':

    #s = SerialEnumerator()
    #s.open('ttyUSB0')
    #r = s.write([0x43, 0x78, 0x1e, 0x07, 254])
    #pprint.pprint( r)
    #s.printstr("READ SONAR Sonar3;")
    #for i in range(0x4b):
    #    s.write([0xfc, 0x0a, 0x7d + i, 0x7d + i])
    #    time.sleep(0.12)
    #    s.write([0xfc, 0x0a, 0x64, 0x64])


    #s.write([0xfc, 0x0a, 0x7d + i, 0x7d + i])
    #time.sleep(0.02)

    #s.close()

    r = RadioDongle('ttyUSB0')
    r.buffer = 128
    print r.buffer