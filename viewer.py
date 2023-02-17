#!/usr/bin/env python3

import os
import re
import csv
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import (
    FigureCanvasGTK3Agg as FigureCanvas)
from matplotlib.backends.backend_gtk3 import (
    NavigationToolbar2GTK3 as NavigationToolbar)
import matplotlib as mpl
from gi.repository import Gtk, Gdk, GObject, cairo
import gi
gi.require_version('Gtk', '3.0')

RUNS_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'runs')


def read_runs():
    filename_pattern = re.compile(r"^run\.mon\.(\d{5})\.(.*)\.csv$")

    for (f, num, desc) in (map(g.group, range(3)) for g in map(filename_pattern.match, sorted(os.listdir(RUNS_DIR))) if g):
        if os.path.isfile(os.path.join(RUNS_DIR, f)):
            yield (int(num), desc)


def read_cases_data(num, desc):
    filename = os.path.join(RUNS_DIR, f'run.mon.{num:05}.{desc}.csv')
    with open(filename, 'r', newline='') as csvfile:
        rows = iter(csv.reader(csvfile, dialect='unix'))
        # Discard header
        next(rows)
        for row in rows:
            yield row


class CellRendererLineColor(Gtk.CellRenderer):
    drawn = GObject.Property(type=bool, default=False)
    line_color = GObject.Property(
        type=Gdk.RGBA, default=Gdk.RGBA(1.0, 1.0, 1.0, 1.0))

    def __init__(self):
        Gtk.CellRenderer.__init__(self)

    def do_render(self, cr, widget, background_area, cell_area, flags):
        if self.get_property('drawn') and flags & Gtk.CellRendererState.SELECTED:
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(cell_area.x, cell_area.y,
                         cell_area.width, cell_area.height)
            cr.fill()

            height = cell_area.y + cell_area.height / 2
            cr.move_to(cell_area.x, height)
            cr.line_to(cell_area.x + cell_area.width, height)

            color = self.get_property('line_color')
            cr.set_source_rgba(*color)
            cr.stroke()


class Viewer:
    def __init__(self):
        runs_store = Gtk.ListStore(int, str)
        cases_store = Gtk.ListStore(str, bool, Gdk.RGBA)

        known_cases = dict()
        for run in read_runs():
            runs_store.append(run)
            for data in read_cases_data(*run):
                # Insert case name in a dict instead of a set to preserve the original order:
                known_cases[data[0]] = None
        for case_name in known_cases:
            cases_store.append([case_name, False, Gdk.RGBA()])

        builder = Gtk.Builder()
        builder.add_from_file("viewer-gui.glade")

        runs_view = builder.get_object('runs_view')
        runs_view.set_model(runs_store)
        runs_view.append_column(Gtk.TreeViewColumn(
            'Seq', text=0, cell_renderer=Gtk.CellRendererText()))
        runs_view.append_column(Gtk.TreeViewColumn(
            'Description', text=1, cell_renderer=Gtk.CellRendererText()))
        self.runs_selection = runs_view.get_selection()
        self.runs_selection.select_all()

        cases_view = builder.get_object('cases_view')
        cases_view.set_model(cases_store)
        cases_view.append_column(Gtk.TreeViewColumn(
            'Case', text=0, cell_renderer=Gtk.CellRendererText()))
        cases_view.append_column(Gtk.TreeViewColumn(
            'Color', drawn=1, line_color=2, cell_renderer=CellRendererLineColor()))
        self.cases_selection = cases_view.get_selection()
        self.cases_selection.select_all()

        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(1, 1, 1)

        box = builder.get_object("graph_box")

        # Add canvas to vbox
        self.canvas = FigureCanvas(self.fig)  # a Gtk.DrawingArea
        box.pack_start(self.canvas, True, True, 0)

        win = builder.get_object("main_window")

        # Create toolbar
        toolbar = NavigationToolbar(self.canvas, win)
        box.pack_start(toolbar, False, False, 0)

        builder.connect_signals({'onQuit': Gtk.main_quit,
                                'onDataSelection': self.refresh_data})

        self.refresh_data()

        win.show_all()

    def refresh_data(self, *args):
        (cases, sel_cases) = self.cases_selection.get_selected_rows()
        cases_vals = (cases.get_iter(p) for p in sel_cases)
        cases_vals = {cases.get(it, 0)[0]: (it, []) for it in cases_vals}

        (runs, sel_runs) = self.runs_selection.get_selected_rows()
        sel_runs = [runs.get(runs.get_iter(p), 0, 1) for p in sel_runs]
        for run in sel_runs:
            for (_, row) in cases_vals.values():
                row.append(None)
            for case in read_cases_data(*run):
                try:
                    (_, row) = cases_vals[case[0]]
                except KeyError:
                    continue

                if case[1] == 'Success':
                    row[-1] = float(case[3]) + float(case[4])

        x = list(range(len(sel_runs)))
        self.ax.clear()
        self.ax.set_xticks(x, next(zip(*sel_runs)))
        for (case_name, (it, values)) in cases_vals.items():
            if all(v is None for v in values):
                cases.set(it, [1], [False])
                continue

            l = self.ax.plot(x, values, 'o-', label=case_name)[0]

            # Set the color in the list view to render the legend
            color = Gdk.RGBA(*mpl.colors.to_rgba(l.get_color()))
            cases.set(it, [1, 2], [True, color])
        # TODO: display line case name upon hovering

        self.canvas.draw()


def main():
    viewer = Viewer()
    Gtk.main()


if __name__ == '__main__':
    main()
