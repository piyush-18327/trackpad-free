import ctypes
import gc
import struct
import unittest
from unittest.mock import patch

from gestures import Frame
import hidraw
from gesture_input import INPUT, KEYBDINPUT, MOUSEINPUT


class RawInputTests(unittest.TestCase):
    def test_native_layouts(self):
        self.assertEqual(ctypes.sizeof(hidraw.HIDP_VALUE_CAPS),72)
        self.assertEqual(ctypes.sizeof(hidraw.HIDP_CAPS),64)
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

    def test_hid_batch_preserves_lift_and_all_frames(self):
        monitor=hidraw.RawInputMonitor(1)
        class Parser:
            def parse(self,report,device): return Frame(float(report[0]),(),device=device)
        monitor.parsers[123]=Parser()
        header=hidraw.RAWINPUTHEADER(2,0,123,0)
        payload=bytes(header)+struct.pack('<II',1,3)+b'\x01\x02\x03'
        def read(handle,command,buffer,size,header_size):
            size._obj.value=len(payload)
            if buffer is None: return 0  # successful sizing call returns ZERO
            ctypes.memmove(buffer,payload,len(payload))
            return len(payload)
        with patch.object(hidraw.user32,'GetRawInputData',read):
            frames=monitor.read(99)
        self.assertEqual([f.time for f in frames],[1,2,3])
        self.assertEqual(monitor.errors,0)

    def test_malformed_batch_is_ignored(self):
        monitor=hidraw.RawInputMonitor(1)
        header=hidraw.RAWINPUTHEADER(2,0,123,0)
        payload=bytes(header)+struct.pack('<II',112,5)+b'\x05'
        monitor.parsers[123]=object()
        def read(handle,command,buffer,size,header_size):
            size._obj.value=len(payload)
            if buffer is None: return 0
            ctypes.memmove(buffer,payload,len(payload)); return len(payload)
        with patch.object(hidraw.user32,'GetRawInputData',read): self.assertEqual(monitor.read(99),[])
        self.assertEqual(monitor.errors,1)

    def test_tip_and_confidence_are_members_not_boolean_length(self):
        with patch.object(hidraw.TouchpadParser,'_read_value_caps'):
            parser=hidraw.TouchpadParser(ctypes.create_string_buffer(10),5)
        def usages(kind,page,link,buffer,length,preparsed,report,size):
            self.assertGreaterEqual(length._obj.value,2)
            buffer[0]=0x47; length._obj.value=1
            return hidraw.HIDP_STATUS_SUCCESS
        with patch.object(hidraw.hid,'HidP_GetUsages',usages):
            values=parser._usages(b'\x05',1)
        self.assertIn(0x47,values)
        self.assertNotIn(0x42,values)

    def test_normalization_honors_nonzero_and_signed_minimum(self):
        with patch.object(hidraw.TouchpadParser,'_read_value_caps'):
            parser=hidraw.TouchpadParser(ctypes.create_string_buffer(10),5)
        parser.axes={(1,0x30):(-100,100,16),(1,0x31):(100,300,16)}
        self.assertEqual(parser._coordinate(0xFF9C,1,0x30),0)
        self.assertEqual(parser._coordinate(200,1,0x31),.5)
        with self.assertRaises(ValueError): parser._coordinate(400,1,0x31)
