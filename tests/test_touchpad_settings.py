"""Transactions use an in-memory registry; never mutate the runner's settings."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import touchpad_settings as ptp


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.registry={"": {"TapsEnabled":{"type":4,"value":1}, "Unrelated":{"type":1,"value":"user"}}}
        self.flags={"tap":True,"two_tap":False,"pan":True,"zoom":True,"reverse":True}
        def snapshot(): return {"registry":deepcopy(self.registry),"flags":deepcopy(self.flags)}
        def write(k,n,item):
            if item is None: self.registry[k].pop(n,None)
            else: self.registry[k][n]=deepcopy(item)
        def flags(values):
            self.flags.update(values)
            # SPI writes unrelated defaults too, just as the live experiment did.
            self.registry['']['TapsEnabled']={'type':4,'value':0xFFFFFFFF if self.flags['tap'] else 0}
            self.registry['']['FeedbackIntensity']={'type':4,'value':50}
        for target,replacement in [("data_dir",lambda:Path(self.folder.name)),("snapshot",snapshot),
                                  ("registry_snapshot",lambda:deepcopy(self.registry)),("write_value",write),
                                  ("set_flags",flags),("logon_id",lambda:"session-a")]:
            p=patch.object(ptp,target,replacement); p.start(); self.addCleanup(p.stop)

    def test_exact_round_trip_including_spi_side_effects_and_absent_values(self):
        before=deepcopy(self.registry),deepcopy(self.flags)
        ptp.apply_transaction('test',{'tap':False},[{'key':'','name':'ThreeFingerUp','after':{'type':4,'value':2}}])
        self.assertEqual(self.registry['']['ThreeFingerUp']['value'],2)
        ptp.restore_transaction('test')
        self.assertEqual((self.registry,self.flags),before)

    def test_repeat_apply_preserves_original_backup(self):
        ptp.apply_transaction('test',{'tap':False},[])
        with self.assertRaises(RuntimeError): ptp.apply_transaction('test',{'tap':True},[])
        ptp.restore_transaction('test')
        self.assertTrue(self.flags['tap'])

    def test_restore_does_not_overwrite_unrelated_later_user_edit(self):
        ptp.apply_transaction('test',{'tap':False},[])
        self.registry['']['Unrelated']['value']='new choice'
        ptp.restore_transaction('test')
        self.assertEqual(self.registry['']['Unrelated']['value'],'new choice')

    def test_failed_readback_rolls_back(self):
        before=deepcopy(self.registry)
        original=ptp.write_value
        def faulty(k,n,item):
            if n!='ThreeFingerUp': original(k,n,item)
        with patch.object(ptp,'write_value',faulty):
            with self.assertRaises(RuntimeError):
                ptp.apply_transaction('test',{'tap':False},[{'key':'','name':'ThreeFingerUp','after':{'type':4,'value':2}}])
        self.assertEqual(self.registry,before)


class StructureTests(unittest.TestCase):
    def test_spi_v1_bitfield_layout(self):
        import ctypes
        self.assertEqual(ctypes.sizeof(ptp.TOUCHPAD_PARAMETERS),44)
        self.assertEqual(ptp.TOUCHPAD_PARAMETERS.settingsFlags.offset,16)

    def test_measured_mapping_contains_explicit_directions(self):
        data=__import__('json').loads(Path(ptp.__file__).with_name('gesture_mapping.json').read_text())
        values={c['name']:c['after']['value'] for c in data['profiles']['mac']}
        self.assertEqual(values,{'ThreeFingerUp':2,'ThreeFingerDown':3,'ThreeFingerLeft':4,'ThreeFingerRight':4,'ThreeFingerSlideEnabled':2})


class BuildTests(unittest.TestCase):
    def build(self, number):
        from types import SimpleNamespace
        return patch.object(ptp.sys, "getwindowsversion", lambda: SimpleNamespace(build=number))

    def test_measured_build_has_no_note(self):
        measured = ptp.mapping()["build"]
        with self.build(measured):
            self.assertEqual(ptp.mapping_note(), "")

    def test_other_windows_11_builds_work_with_a_verify_note(self):
        with self.build(26100):
            self.assertTrue(ptp.action_changes("three_none"))
            self.assertIn("26100", ptp.mapping_note())

    def test_windows_10_is_refused(self):
        with self.build(19045):
            with self.assertRaises(RuntimeError):
                ptp.action_changes("mac")


class TwoFingerTapHoldTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.native = {"two_tap": True}
        for target, replacement in (("data_dir", lambda: Path(self.folder.name)),
                                    ("native_two_tap", lambda: self.native["two_tap"]),
                                    ("set_flags", self.native.update)):
            p = patch.object(ptp, target, replacement); p.start(); self.addCleanup(p.stop)

    def test_smart_zoom_no_longer_saves_a_two_tap_change(self):
        settings = {"smart_zoom": True, "three_finger_drag": False, "lookup": False, "launchpad": False}
        self.assertEqual(ptp.conflict_plan(settings), ({}, []))

    def test_hold_and_release_restore_the_users_setting(self):
        ptp.hold_two_finger_tap()
        self.assertFalse(self.native["two_tap"])
        self.assertTrue(ptp.two_finger_tap_held())
        ptp.release_two_finger_tap()
        self.assertTrue(self.native["two_tap"])
        self.assertFalse(ptp.two_finger_tap_held())

    def test_hold_reasserts_but_keeps_the_original(self):
        ptp.hold_two_finger_tap()
        self.native["two_tap"] = True  # e.g. another tool switched it back on
        ptp.hold_two_finger_tap()
        self.assertFalse(self.native["two_tap"])
        ptp.release_two_finger_tap()
        self.assertTrue(self.native["two_tap"])

    def test_user_who_had_it_off_keeps_it_off(self):
        self.native["two_tap"] = False
        ptp.hold_two_finger_tap()
        ptp.release_two_finger_tap()
        self.assertFalse(self.native["two_tap"])
