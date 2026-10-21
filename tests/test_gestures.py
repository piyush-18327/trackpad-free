"""Synthetic hardware-free contact streams: recognition and rejection."""

import unittest

from gestures import Action, Contact, Frame, Recognizer, validate


def frame(t, points=(), **kwargs):
    return Frame(t, tuple(Contact(i, x, y) for i, (x, y) in enumerate(points)), **kwargs)


TWO = ((.4, .4), (.5, .4))
THREE = TWO + ((.6, .4),)
FOUR = ((.3, .3), (.7, .3), (.3, .7), (.7, .7))
FIVE = FOUR + ((.5, .85),)


def move(points, dx=0, dy=0):
    return tuple((x+dx, y+dy) for x, y in points)


class GestureTests(unittest.TestCase):
    def test_default_off(self):
        r = Recognizer()
        for t, p in [(0, THREE), (.1, move(THREE,.1)), (.2, ())]:
            self.assertEqual(r.feed(frame(t,p)), [])

    def test_drag_moves_and_releases_after_grace_without_reports(self):
        r=Recognizer({"three_finger_drag":True})
        self.assertEqual(r.feed(frame(0,THREE)),[])
        a=r.feed(frame(.1,move(THREE,.02)))
        self.assertEqual([x.kind for x in a],["left_down","move"])
        self.assertAlmostEqual(a[1].dx,.02)
        self.assertEqual(r.feed(frame(.2,())),[])
        self.assertEqual(r.tick(.69),[])
        self.assertEqual(r.tick(.71),[Action("left_up")])
        self.assertEqual(r.tick(2),[])

    def test_drag_retouch_during_grace_does_not_jump(self):
        r=Recognizer({"three_finger_drag":True})
        r.feed(frame(0,THREE)); r.feed(frame(.1,move(THREE,.02)))
        r.feed(frame(.2,()))
        a=r.feed(frame(.3,move(THREE,.2)))
        self.assertTrue(all(x.kind=="move" and x.dx==0 and x.dy==0 for x in a))
        a=r.feed(frame(.4,move(THREE,.23)))
        self.assertAlmostEqual(a[0].dx,.03)

    def test_rest_does_not_start_drag(self):
        r=Recognizer({"three_finger_drag":True})
        r.feed(frame(0,THREE))
        for t in (.1,.3,.6,.8): self.assertEqual(r.feed(frame(t,THREE)),[])
        self.assertEqual(r.feed(frame(.9,move(THREE,.1))),[])

    def test_palm_cancels_drag_and_suppresses_until_lift(self):
        r=Recognizer({"three_finger_drag":True,"lookup":True})
        r.feed(frame(0,THREE)); r.feed(frame(.1,move(THREE,.02)))
        palm=Frame(.2,(Contact(0,.5,.4,confidence=False),Contact(1,.6,.4),Contact(2,.7,.4)))
        self.assertEqual(r.feed(palm),[Action("left_up")])
        self.assertEqual(r.feed(frame(.25,THREE)),[])
        self.assertEqual(r.feed(frame(.3,())),[])

    def test_resting_palm_never_counts_as_three_fingers(self):
        r=Recognizer({"three_finger_drag":True})
        for t, dx in [(0,0),(.1,.1)]:
            self.assertEqual(r.feed(Frame(t,(Contact(0,.4+dx,.4),Contact(1,.5+dx,.4),Contact(2,.6+dx,.4,confidence=False)))),[])

    def test_device_switch_and_cancel_release_button(self):
        for cancel in (True,False):
            r=Recognizer({"three_finger_drag":True})
            r.feed(frame(0,THREE)); r.feed(frame(.1,move(THREE,.02)))
            self.assertIn(Action("left_up"), r.cancel() if cancel else r.feed(frame(.2,(),device=9)))

    def test_lost_stream_watchdog_releases(self):
        r=Recognizer({"three_finger_drag":True})
        r.feed(frame(0,THREE)); r.feed(frame(.1,move(THREE,.02)))
        self.assertEqual(r.tick(1.2),[Action("left_up")])

    def test_smart_zoom_double_tap_then_reset(self):
        r=Recognizer({"smart_zoom":True})
        results=[]
        for start in (0,.22,1,1.22):
            results+=r.feed(frame(start,TWO))
            results+=r.feed(frame(start+.1,()))
        # Zoom in vs reset is decided per window by the output side (gesture_input).
        self.assertEqual(results,[Action("smart_zoom"),Action("smart_zoom")])

    def test_tap_then_quick_scroll_still_right_clicks(self):
        r=Recognizer({"smart_zoom":True})
        r.feed(frame(0,TWO)); r.feed(frame(.1,()))
        r.feed(frame(.2,TWO))
        self.assertEqual(r.feed(frame(.25,move(TWO,dy=.08))),[Action("right_click")])
        self.assertEqual(r.feed(frame(.3,())),[])
        self.assertEqual(r.tick(2),[])

    def test_single_two_finger_tap_right_clicks_after_deadline(self):
        r=Recognizer({"smart_zoom":True})
        r.feed(frame(0,TWO)); r.feed(frame(.1,()))
        self.assertEqual(r.tick(.46),[Action("right_click")])
        self.assertEqual(r.tick(.5),[])

    def test_two_finger_scroll_and_return_is_not_smart_zoom(self):
        r=Recognizer({"smart_zoom":True})
        for start in (0,.4):
            for dt,p in [(0,TWO),(.08,move(TWO,dy=.08)),(.12,TWO),(.15,())]:
                self.assertEqual(r.feed(frame(start+dt,p)),[])
        self.assertEqual(r.tick(2),[])

    def test_physical_click_does_not_generate_tap(self):
        r=Recognizer({"smart_zoom":True})
        r.feed(frame(0,TWO,button=True))
        self.assertEqual(r.feed(frame(.1,())),[])
        self.assertEqual(r.tick(1),[])

    def test_edge_swipe_once_and_reject_middle_or_vertical(self):
        for points, dx, dy, expected in [(((.96,.4),(.94,.5)),-.2,0,[Action("notifications")]),
                                         (TWO,-.2,0,[]), (((.96,.4),(.94,.5)),0,.2,[])]:
            r=Recognizer({"notification_center":True})
            r.feed(frame(0,points))
            self.assertEqual(r.feed(frame(.1,move(points,dx,dy))),expected)
            self.assertEqual(r.feed(frame(.2,move(points,dx,dy))),[])

    def test_pinch_spread_and_parallel_translation(self):
        for ratio,kind in [(.6,"start"),(1.4,"desktop")]:
            r=Recognizer({"launchpad":True})
            r.feed(frame(0,FOUR))
            p=tuple((.5+(x-.5)*ratio,.5+(y-.5)*ratio) for x,y in FOUR)
            self.assertEqual(r.feed(frame(.1,p)),[Action(kind)])
            self.assertEqual(r.feed(frame(.2,p)),[])
        r=Recognizer({"launchpad":True})
        r.feed(frame(0,FOUR))
        self.assertEqual(r.feed(frame(.1,move(FOUR,.15))),[])

    def test_four_swipes_when_engine_owns_four_fingers(self):
        r=Recognizer({"launchpad":True},four_swipes=True)
        r.feed(frame(0,FOUR))
        self.assertEqual(r.feed(frame(.1,move(FOUR,dy=-.15))),[Action("task_view")])

    def test_three_tap_lookup_vs_drag_priority(self):
        r=Recognizer({"lookup":True,"three_finger_drag":True})
        r.feed(frame(0,THREE))
        self.assertEqual(r.feed(frame(.1,())),[Action("lookup")])
        r.feed(frame(1,THREE))
        self.assertEqual(r.feed(frame(1.1,move(THREE,.05)))[0],Action("left_down"))
        self.assertNotIn(Action("lookup"),r.feed(frame(1.2,())))

    def test_staggered_landing_and_lifting(self):
        r=Recognizer({"lookup":True})
        for t,p in [(0,THREE[:1]),(.02,THREE[:2]),(.04,THREE),(.1,THREE[:2]),(.12,THREE[:1])]:
            self.assertEqual(r.feed(frame(t,p)),[])
        self.assertEqual(r.feed(frame(.14,())),[Action("lookup")])

    def five_taps(self, r, starts, points=FIVE):
        results = []
        for start in starts:
            results += r.feed(frame(start, points))
            results += r.feed(frame(start + .1, ()))
        return results

    def test_five_finger_double_tap_takes_a_screenshot_once(self):
        r = Recognizer({"five_finger_screenshot": True})
        self.assertEqual(self.five_taps(r, (0, .4)), [Action("screenshot")])
        self.assertEqual(r.tick(5), [])

    def test_five_finger_double_tap_is_off_by_default(self):
        self.assertEqual(self.five_taps(Recognizer(), (0, .4)), [])

    def test_single_or_slow_five_finger_taps_do_nothing(self):
        r = Recognizer({"five_finger_screenshot": True})
        self.assertEqual(self.five_taps(r, (0,)), [])
        self.assertEqual(r.tick(.5), [])
        self.assertEqual(self.five_taps(r, (2, 3)), [])  # second lift 1 s after the first

    def test_other_touch_between_five_finger_taps_breaks_the_double_tap(self):
        r = Recognizer({"five_finger_screenshot": True})
        self.assertEqual(self.five_taps(r, (0,)) + self.five_taps(r, (.2,), TWO) + self.five_taps(r, (.35,)), [])

    def test_four_fingers_or_moving_fingers_do_not_screenshot(self):
        r = Recognizer({"five_finger_screenshot": True})
        self.assertEqual(self.five_taps(r, (0, .4), FOUR), [])
        r = Recognizer({"five_finger_screenshot": True})
        results = r.feed(frame(0, FIVE)) + r.feed(frame(.05, move(FIVE, .05))) + r.feed(frame(.1, ()))
        self.assertEqual(results + self.five_taps(r, (.4,)), [])

    def test_invalid_settings(self):
        for invalid in ({"edge_width":float('nan')},{"tap_max_time":True},{"lookup":1},{"x":True}):
            with self.assertRaises(ValueError): validate(invalid)


if __name__ == '__main__':
    unittest.main()
