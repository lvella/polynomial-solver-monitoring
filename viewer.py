#!/usr/bin/env python3

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import (
    FigureCanvasGTK3Agg as FigureCanvas)
from matplotlib.backends.backend_gtk3 import (
    NavigationToolbar2GTK3 as NavigationToolbar)
from gi.repository import Gtk
import gi
gi.require_version('Gtk', '3.0')


def main():
    builder = Gtk.Builder()
    builder.add_from_file("viewer-gui.glade")
    win = builder.get_object("main_window")

    win.connect("delete-event", Gtk.main_quit)

    fig = Figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(1, 1, 1)
    t = np.arange(0.0, 3.0, 0.01)
    s = np.sin(2*np.pi*t)
    ax.plot(t, s)

    vbox = builder.get_object("graph_box")

    # Add canvas to vbox
    canvas = FigureCanvas(fig)  # a Gtk.DrawingArea
    vbox.pack_start(canvas, True, True, 0)

    # Create toolbar
    toolbar = NavigationToolbar(canvas, win)
    vbox.pack_start(toolbar, False, False, 0)

    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
