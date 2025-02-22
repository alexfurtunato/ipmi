import time
import datetime
import pickle
import xml.etree.ElementTree as ET
import requests

def ToSigned(Num, signedbitB):
    if signedbitB > 0:
        # positive 
        if ( Num%(0x01<<signedbitB)/(0x01<<(signedbitB-1)) ) < 1:
            return Num%(0x01<<signedbitB-1)
        # negative
        else:
            temp = (Num%(0x01<<signedbitB-1)) ^ ((0x01<<signedbitB-1)-1)
            return (-1-temp)
    else:
        return Num

class IPMI:
    def __init__(self, server, user="admin", password="admin"):
        self.server = server
        self.formPower = {"POWER_CONSUMPTION.XML":"(0,0)", "time_stamp":"","_":""}
        self.formSource = {"Get_PSInfoReadings.XML":"(0,0)","time_stamp":"","_":""}
        self.formSensors = {"SENSOR_INFO.XML":"(1,ff)","time_stamp":"","_":""}
        self.subpages = ["servh_psinfo","monitor_pw_comsumption"]
        self.cookies = {"langSetFlag":"0","language":"English","SID":"",
                        "mainpage":"health","subpage":self.subpages[1]}
        
        self.conn = False
        self.user = user
        self.password = password

        self.login()

    def login(self):
        try:
            login = requests.post(self.server+"/cgi/login.cgi",
                    data = {"name":self.user,"pwd":self.password})

            if "SID" in login.cookies.get_dict().keys():
                self.cookies["SID"] = login.cookies.get_dict()["SID"]
                self.conn = True
            else:
                print("Wrong username or password")
        except requests.exceptions.RequestException as e:
            print("Connection error", e)

    def get_data(self):
        if not self.conn:
            print("Not connected")
            return
        now = datetime.datetime.now()
        tstamp = time.mktime(now.timetuple())
        self.formPower["time_stamp"] = tstamp
        self.formSource["time_stamp"] = tstamp
        self.formSensors["time_stamp"] = tstamp
        try:
            rPower = requests.post(self.server+"/cgi/ipmi.cgi", data= self.formPower, 
                                    cookies=self.cookies)
            rSource = requests.post(self.server+"/cgi/ipmi.cgi", data= self.formSource, 
                                    cookies=self.cookies)
            rSensors = requests.post(self.server+"/cgi/ipmi.cgi", data= self.formSensors, 
                                    cookies=self.cookies)
        except requests.exceptions.RequestException as e:
            print("Connection error", e)

        return self.processXML(rPower, rSource, rSensors)

    def processXML(self, rPower, rSource, rSensors):
        sensor_now = {}
        sources = []
        pwd = []
        ipmiS = ET.fromstring(rSource.content)
        ipmiP = ET.fromstring(rPower.content)
        ipmiI = ET.fromstring(rSensors.content)
        cont = 1

        for child in ipmiS:
            for item in child:
                ps = item.attrib
                if ps["a_b_PS_Status_I2C"] != '1': continue

                data_now = {}
                data_now["font_n"] = cont
                data_now["acInVoltage"] = int(ps["acInVoltage"], 16)
                data_now["acInCurrent"] = int(ps["acInCurrent"], 16)/1000.0
                data_now["acInPower"] = int(ps["acInPower"], 16)
                data_now["dc12OutVoltage"] = int(ps["dc12OutVoltage"], 16)/10.0
                data_now["dc12OutCurrent"] = int(ps["dc12OutCurrent"], 16)/1000.0
                data_now["dcOutPower"] = int(ps["dcOutPower"], 16)
                data_now["temp1"] = int(ps["temp1"], 16)
                data_now["temp2"] = int(ps["temp2"], 16)

                sources.append(data_now)

                cont += 1

        for child in ipmiI:
            for item in child:
                ps = item.attrib
                if "Vcpu1"in ps["NAME"] or"Vcpu2"in ps["NAME"]:
                    #					print(ps["NAME"])

                    UnitType1 = int(ps["UNIT1"], 16)
                    AnalogDataFormat = UnitType1 >> 6
                    if AnalogDataFormat == 0x02:
                        raw_data = hex(ToSigned(int(ps["READING"][:2], 16), 8))
                    else:
                        raw_data = ps["READING"][:2]

                    m = ps["M"]
                    b = ps["B"]
                    rb = ps["RB"]

                    # change sequense of lsb and msb into 10b char
                    M_raw = ((int(m,16)&0xC0) << 2) + ( int(m,16) >> 8)
                    B_raw = ((int(b,16)&0xC0) << 2) + ( int(b,16) >> 8)

                    Km_raw = int(rb,16) >> 4
                    Kb_raw = (int(rb,16) & 0x0F)

                    M_data = ToSigned(M_raw, 10)
                    B_data = ToSigned(B_raw, 10)
                    Km_data = ToSigned(Km_raw, 4)
                    Kb_data = ToSigned(Kb_raw, 4)

                    sensor_data = (M_data*int(raw_data, 16) + B_data*10**Kb_data) * 10**Km_data
                    sensor_now[ps["NAME"]]= sensor_data

        for child in ipmiP:
            if child.tag == "NOW":
                now = child.attrib
                pwd.append({k:int(v) for k, v in now.items()})

        mix= {"sources":sources,"power":pwd,"sensor": sensor_now}
        return mix
