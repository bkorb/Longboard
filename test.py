import pyvesc
from pyvesc.protocol.base import VESCMessage
from pyvesc.VESC.messages import VedderCmd as vc

for i in range(50):
    try:
        VESCMessage.msg_type(i)
        print(f"{vc(i).name}(\"{vc(i).name}\"),")
    except KeyError:
        pass