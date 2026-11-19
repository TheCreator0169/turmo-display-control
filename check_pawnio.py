import pythonnet
pythonnet.load('coreclr')
import clr
import sys
sys.path.append(r'C:\Program Files\LibreHardwareMonitor.NET10')
clr.AddReference('LibreHardwareMonitorLib')
from LibreHardwareMonitor.PawnIo import PawnIo
from System import Type

t = Type.GetType('LibreHardwareMonitor.PawnIo.PawnIo, LibreHardwareMonitorLib')
for m in t.GetMethods():
    if m.IsPublic and ('Install' in m.Name or 'install' in m.Name or 'Start' in m.Name or 'Load' in m.Name):
        params = ', '.join([f'{p.ParameterType.Name} {p.Name}' for p in m.GetParameters()])
        print(f'{m.Name}({params}) -> {m.ReturnType.Name}')