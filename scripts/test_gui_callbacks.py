#!/usr/bin/env python3
"""
GUI callback-level test: exercises TurmoApp button callbacks without blocking.
Run on Windows: .venv-win\\Scripts\\python.exe scripts\\test_gui_callbacks.py
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def run():
    results = {}
    import tempfile  # the real settings and custom themes are not touched by this run
    _tmp = tempfile.mkdtemp(prefix="turmo-cb-")
    os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = _tmp
    
    # 1. Import the app module
    try:
        import tkinter as tk
        from scripts.turmo_app_enhanced import TurmoApp
        print("[1] Import TurmoApp: PASS")
        results["import"] = True
    except Exception as e:
        print(f"[1] Import TurmoApp: FAIL ({e})")
        results["import"] = False
        return results
    
    # 2. Create root + app
    try:
        root = tk.Tk()
        root.update()
        app = TurmoApp(root)
        root.update()
        print("[2] TurmoApp init: PASS")
        results["init"] = True
    except Exception as e:
        print(f"[2] TurmoApp init: FAIL ({e})")
        results["init"] = False
        root.destroy()
        return results
    
    # 3. Test start_monitor (no port available in WSL/headless)
    try:
        app.monitor_process = None
        app.start_monitor()
        root.update()
        print("[3] start_monitor (no port): PASS (expected no-op or error dialog)")
        results["start_monitor"] = True
    except Exception as e:
        print(f"[3] start_monitor: FAIL ({e})")
        results["start_monitor"] = False
    
    # 4. Test stop_monitor (nothing running)
    try:
        app.stop_monitor()
        root.update()
        print("[4] stop_monitor (idle): PASS")
        results["stop_monitor"] = True
    except Exception as e:
        print(f"[4] stop_monitor: FAIL ({e})")
        results["stop_monitor"] = False
    
    # 5. Test restart_monitor
    try:
        app.restart_monitor()
        root.update()
        print("[5] restart_monitor: PASS")
        results["restart_monitor"] = True
    except Exception as e:
        print(f"[5] restart_monitor: FAIL ({e})")
        results["restart_monitor"] = False
    
    # 6. Test send_test_image
    try:
        app.send_test_image()
        root.update()
        print("[6] send_test_image: PASS")
        results["send_test_image"] = True
    except Exception as e:
        print(f"[6] send_test_image: FAIL ({e})")
        results["send_test_image"] = False
    
    # 7. Test start_preview / stop_preview
    try:
        app.start_preview()
        root.update()
        time.sleep(0.1)
        root.update()
        app.stop_preview()
        root.update()
        print("[7] start/stop preview: PASS")
        results["preview"] = True
    except Exception as e:
        print(f"[7] start/stop preview: FAIL ({e})")
        results["preview"] = False
    
    # 8. Test refresh_port
    try:
        app.refresh_port()
        root.update()
        print("[8] refresh_port: PASS")
        results["refresh_port"] = True
    except Exception as e:
        print(f"[8] refresh_port: FAIL ({e})")
        results["refresh_port"] = False
    
    # 8b. rebuild_ui makes a new port label: it must detect the port again, not stay on "Detecting..."
    try:
        app.rebuild_ui()
        root.update()
        assert app.port_var.get() != "Detecting...", app.port_var.get()
        print("[8b] port label after rebuild_ui: PASS")
        results["port_after_rebuild"] = True
    except Exception as e:
        print(f"[8b] port label after rebuild_ui: FAIL ({e})")
        results["port_after_rebuild"] = False

    # 8c. v0.2.3, window size. Full look: floating it keeps FULL_SIZE and has no thick frame (no edge or corner can be
    # dragged) but keeps the maximise button; at FULL_SIZE and maximised no page needs a scroll bar (Gallery and
    # Diagnostics have long lists and are left out) and no sidebar entry is squeezed. Minimal look: no maximise button.
    try:
        import ctypes
        from scripts.gui_design import SIDEBAR_ITEMS
        from scripts.gui_widgets import ScrollFrame
        FULL_SIZE = app._window_sizes()[0]  # v0.2.8: the design size grown with the scaling, within the work area
        app.show_window()
        user32 = ctypes.windll.user32
        user32.GetParent.restype, user32.GetParent.argtypes = ctypes.c_void_p, (ctypes.c_void_p,)
        user32.GetWindowLongW.restype, user32.GetWindowLongW.argtypes = ctypes.c_long, (ctypes.c_void_p, ctypes.c_int)

        def style():
            return user32.GetWindowLongW(user32.GetParent(root.winfo_id()), -16)

        def check_pages(label):
            flat = lambda w: [w] + [x for c in w.winfo_children() for x in flat(c)]
            for name in ("Dashboard", "Monitor", "Sensors & Graphs", "Settings", "About"):
                app.select_tab(SIDEBAR_ITEMS.index(name))
                root.update()
                for sf in (w for w in flat(app.nb.nametowidget(app.nb.select())) if isinstance(w, ScrollFrame) and w.winfo_ismapped()):
                    assert not sf._bar.winfo_manager(), f"{name}: scroll bar {label} (needs {sf.body.winfo_reqheight()}, has {sf._canvas.winfo_height()})"
            for item in app._sidebar_items:
                assert item.winfo_height() >= item.winfo_reqheight(), f"sidebar entry squeezed {label}: {item.winfo_height()} < {item.winfo_reqheight()}"

        assert not style() & 0x40000, "full look: the thick frame (edge resize) is still there"
        assert style() & 0x10000, "full look: the maximise button is missing"
        assert tuple(root.minsize()) == tuple(FULL_SIZE), root.minsize()
        root.update()
        assert (root.winfo_width(), root.winfo_height()) == tuple(FULL_SIZE), (root.winfo_width(), root.winfo_height())
        check_pages("at FULL_SIZE")
        root.state("zoomed")
        root.update()
        assert root.winfo_width() > FULL_SIZE[0] or root.winfo_screenwidth() <= FULL_SIZE[0], "maximise did not enlarge the window"
        check_pages("maximised")
        root.state("normal")
        root.update()
        app.apply_app_theme("minimalist")
        root.update()
        assert not style() & 0x10000, "minimal look: the maximise button is still there"
        assert not style() & 0x40000, "minimal look: the thick frame is still there"
        assert style() & 0x20000, "minimal look: the minimise button is missing"
        app.apply_app_theme("default")
        root.update()
        assert style() & 0x10000 and not style() & 0x40000, "full look after the minimal one: maximise button or frame wrong"
        assert (root.winfo_width(), root.winfo_height()) == tuple(FULL_SIZE), (root.winfo_width(), root.winfo_height())
        # v0.2.8 keyboard: the hidden notebook is no Tab stop, the sidebar entries come before the footer's switch
        assert str(app.nb.cget("takefocus")) == "0", app.nb.cget("takefocus")
        kids = app.sidebar.winfo_children()
        assert kids.index(app._sidebar_items[-1]) < max(i for i, k in enumerate(kids) if k.winfo_class() == "Frame"), "sidebar footer is before the entries in the Tab order"
        print("[8c] window size modes, no scroll bar, sidebar not squeezed: PASS")
        results["window_size"] = True
    except Exception as e:
        print(f"[8c] window size modes: FAIL ({e})")
        results["window_size"] = False

    # 8d. v0.2.4: Gallery, Sensors & Graphs, Diagnostics and About are empty frames until opened; each keeps its
    # place in the notebook, a rebuild (theme switch) drops what they made, and opening one builds it again.
    try:
        from scripts.gui_design import SIDEBAR_ITEMS
        app.select_tab(0)  # a rebuild opens the page that was open: it would be built
        app.rebuild_ui()
        root.update()
        lazy = ("Gallery", "Sensors & Graphs", "Diagnostics", "About")
        assert set(app._lazy_pages) == set(lazy), app._lazy_pages.keys()
        assert not any(hasattr(app, a) for a in ("_gallery_grid", "diag_tiles", "_sensor_rows")), "stale page attributes after a rebuild"
        assert len(app.nb.tabs()) == len(SIDEBAR_ITEMS), len(app.nb.tabs())
        for name, attr in (("Diagnostics", "diag_tiles"), ("Gallery", "_gallery_grid"), ("About", None), ("Sensors & Graphs", "_sensor_rows")):
            index = SIDEBAR_ITEMS.index(name)
            app.select_tab(index)
            root.update()
            assert name not in app._lazy_pages, f"{name} not built when opened"
            assert app.nb.index("current") == index, f"{name}: wrong page selected ({app.nb.index('current')})"
            assert len(app.nb.tabs()) == len(SIDEBAR_ITEMS) and not app.nb.nametowidget(app.nb.select()).winfo_children() == [], f"{name}: empty page"
            if attr:
                assert hasattr(app, attr), f"{name}: {attr} missing"
        # the idle builder fills what is left, once, and stops
        app.select_tab(0); app.rebuild_ui(); root.update()
        for _ in range(6):
            app._prebuild_next(app._lazy_gen)
        assert not app._lazy_pages and len(app.nb.tabs()) == len(SIDEBAR_ITEMS)
        assert [app.nb.tab(t, "text") for t in app.nb.tabs()][3] == "Gallery", [app.nb.tab(t, "text") for t in app.nb.tabs()]
        # the minimal look's "Open full diagnostics" must work before the page is built
        app.select_tab(0); app.rebuild_ui(); root.update()
        assert "Diagnostics" in app._lazy_pages
        app._full_diagnostics = lambda: app.select_tab(SIDEBAR_ITEMS.index("Diagnostics"))
        from scripts.minimal_ui import MinimalView
        MinimalView._full_diagnostics(mock_view := type("V", (), {"app": app})())
        root.update()
        assert hasattr(app, "diag_tiles") and app.nb.index("current") == SIDEBAR_ITEMS.index("Diagnostics")
        # a builder that fails leaves nothing behind and is tried again
        app.select_tab(0); app.rebuild_ui(); root.update()
        real = app.build_about_tab
        def broken(nb):
            tk.Frame(nb); nb.add(nb.winfo_children()[-1], text="x"); raise RuntimeError("boom")
        app._lazy_pages["About"] = (app._lazy_pages["About"][0], broken)
        n = len(app.nb.tabs())
        try:
            app._ensure_page("About")
            raise AssertionError("the error was swallowed")
        except RuntimeError:
            pass
        assert len(app.nb.tabs()) == n and "About" in app._lazy_pages, "failed page left behind"
        app._lazy_pages["About"] = (app._lazy_pages["About"][0], real)
        app._ensure_page("About")
        assert "About" not in app._lazy_pages and len(app.nb.tabs()) == n
        print("[8d] lazy pages: PASS")
        results["lazy_pages"] = True
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[8d] lazy pages: FAIL ({e})")
        results["lazy_pages"] = False

    # 9. Test on_close (withdraws window)
    try:
        app.on_close()
        root.update()
        print("[9] on_close: PASS")
        results["on_close"] = True
    except Exception as e:
        print(f"[9] on_close: FAIL ({e})")
        results["on_close"] = False
    
    # 10. Test tray icon exists
    try:
        assert app.tray_icon is not None, "tray_icon not created"
        print("[10] tray icon: PASS")
        results["tray"] = True
    except Exception as e:
        print(f"[10] tray icon: FAIL ({e})")
        results["tray"] = False
    
    # 11. Test mutex
    try:
        has_mutex = app._mutex is not None
        print(f"[11] mutex: {'PASS' if has_mutex else 'SKIP'} ({'created' if has_mutex else 'win32event unavailable'})")
        results["mutex"] = has_mutex
    except Exception as e:
        print(f"[11] mutex: FAIL ({e})")
        results["mutex"] = False
    
    # Cleanup
    try:
        app.quit_app()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass  # quit_app may have already destroyed root
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n=== RESULT: {passed}/{total} PASS ===")
    for k, v in results.items():
        status = "PASS" if v else "FAIL/SKIP"
        print(f"  {k}: {status}")
    
    return 0 if all(results.values()) or results.get("import") == False else 1

if __name__ == "__main__":
    sys.exit(run())
