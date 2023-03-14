#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GObject

import os
import re
import csv
from matplotlib.figure import Figure
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar
import matplotlib as mpl
import math

RUNS_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "runs")


def read_data_sets():
    return [
        data_set
        for data_set in os.listdir(RUNS_DIR)
        if os.path.isdir(os.path.join(RUNS_DIR, data_set))
    ]


def read_runs(data_set):
    filename_pattern = re.compile(r"^run\.mon\.(\d{5})\.(.*)\.csv$")

    for (f, num, desc) in (
        map(g.group, range(3))
        for g in map(
            filename_pattern.match, sorted(os.listdir(os.path.join(RUNS_DIR, data_set)))
        )
        if g
    ):
        if os.path.isfile(os.path.join(RUNS_DIR, data_set, f)):
            yield (int(num), desc)


def read_cases_data(data_set, num, desc):
    filename = os.path.join(RUNS_DIR, data_set, f"run.mon.{num:05}.{desc}.csv")
    with open(filename, "r", newline="") as csvfile:
        rows = iter(csv.reader(csvfile, dialect="unix"))
        # Discard header
        next(rows)
        for row in rows:
            yield row


class DelayedExecutor:
    def __init__(self, function):
        self._function = function
        self._scheduled = False

    def schedule_run(self):
        if not self._scheduled:
            GLib.idle_add(self._do_execute)
            self._scheduled = True

    def _do_execute(self):
        self._function()
        self._scheduled = False

        return False


class CellRendererLineColor(Gtk.CellRenderer):
    drawn = GObject.Property(type=bool, default=False)
    line_color = GObject.Property(type=Gdk.RGBA, default=Gdk.RGBA(1.0, 1.0, 1.0, 1.0))

    def __init__(self):
        Gtk.CellRenderer.__init__(self)

    def do_render(self, cr, widget, background_area, cell_area, flags):
        if self.get_property("drawn") and flags & Gtk.CellRendererState.SELECTED:
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(cell_area.x, cell_area.y, cell_area.width, cell_area.height)
            cr.fill()

            middle_y = cell_area.y + cell_area.height / 2
            middle_x = cell_area.x + cell_area.width / 2

            cr.set_source_rgba(*self.get_property("line_color"))

            cr.arc(middle_x, middle_y, 5, 0, 2 * math.pi)
            cr.fill()

            cr.move_to(cell_area.x, middle_y)
            cr.line_to(cell_area.x + cell_area.width, middle_y)
            cr.stroke()


def new_resizable_column(*args, **kwargs):
    c = Gtk.TreeViewColumn(*args, **kwargs)
    c.set_resizable(True)
    return c


class Viewer:
    def __init__(self):
        self.refresher = DelayedExecutor(self._refresh_data)
        self.selected_line = None

        data_sets = Gtk.ListStore(str)
        for data_set in read_data_sets():
            data_sets.append([data_set])

        self.runs_store = Gtk.ListStore(int, str)
        self.cases_store = Gtk.ListStore(str, bool, Gdk.RGBA)

        builder = Gtk.Builder()
        builder.add_from_file("viewer-gui.glade")

        set_selector = builder.get_object("set_selector")
        set_selector.set_model(data_sets)
        set_selector.set_id_column(0)
        set_selector_renderer = Gtk.CellRendererText()
        set_selector.pack_start(set_selector_renderer, True)
        set_selector.add_attribute(set_selector_renderer, "text", 0)

        runs_view = builder.get_object("runs_view")
        runs_view.set_model(self.runs_store)
        runs_view.append_column(
            new_resizable_column("Seq", text=0, cell_renderer=Gtk.CellRendererText())
        )
        runs_view.append_column(
            new_resizable_column(
                "Description", text=1, cell_renderer=Gtk.CellRendererText()
            )
        )
        self.runs_selection = runs_view.get_selection()

        cases_view = builder.get_object("cases_view")
        cases_view.set_model(self.cases_store)
        c = Gtk.TreeViewColumn(
            "Color", drawn=1, line_color=2, cell_renderer=CellRendererLineColor()
        )
        c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        c.set_expand(False)
        c.set_fixed_width(50)
        c.set_clickable(True)
        cases_view.append_column(c)
        cases_view.append_column(
            new_resizable_column("Case", text=0, cell_renderer=Gtk.CellRendererText())
        )
        self.cases_selection = cases_view.get_selection()

        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.canvas.mpl_connect("motion_notify_event", self.mouse_hover)
        self.fig.canvas.mpl_connect("button_press_event", self.mouse_click)
        self.ax = self.fig.add_subplot(1, 1, 1)

        self.radiobutton_plot_runtime = builder.get_object("radiobutton_plot_runtime")
        self.radiobutton_plot_progress = builder.get_object("radiobutton_plot_progress")
        self.get_data = self.get_runtime_data

        box = builder.get_object("graph_box")

        # Add canvas to vbox
        self.canvas = FigureCanvas(self.fig)  # a Gtk.DrawingArea
        box.pack_start(self.canvas, True, True, 0)

        win = builder.get_object("main_window")

        # Create toolbar
        toolbar = NavigationToolbar(self.canvas, win)
        box.pack_start(toolbar, False, False, 0)

        builder.connect_signals(
            {
                "onQuit": Gtk.main_quit,
                "onDataSetSelected": self.refresh_data_set,
                "onDataSelection": lambda _: self.refresher.schedule_run(),
                "onChangePlotType": self.change_plot_type,
            }
        )

        set_selector.set_active(0)

        win.show_all()

    def change_plot_type(self, button):
        if self.radiobutton_plot_runtime.get_active():
            self.get_data = self.get_runtime_data
        elif self.radiobutton_plot_progress.get_active():
            self.get_data = self.get_progress_data
        self.refresher.schedule_run()

    def get_runtime_data(self, selected_runs, selected_cases):
        for run in selected_runs:
            for (_, row) in selected_cases.values():
                row.append(None)
            for case in read_cases_data(self.selected_data_set, *run):
                try:
                    (_, row) = selected_cases[case[0]]
                except KeyError:
                    continue

                if case[1] == "Success":
                    row[-1] = float(case[3]) + float(case[4])

        self.ax.set_ylabel("Run time (seconds)")
        self.ax.set_yscale("linear")

    def get_progress_data(self, selected_runs, selected_cases):
        for run in selected_runs:
            for (_, row) in selected_cases.values():
                row.append((False, None))
            for case in read_cases_data(self.selected_data_set, *run):
                try:
                    (_, row) = selected_cases[case[0]]
                except KeyError:
                    continue

                row[-1] = (case[1] == "Timedout", int(case[5]))

        for (_, row) in selected_cases.values():
            # We are only interested in cases which are themselves timeouts,
            # and cases immediately before of after timeouts.
            new_row = []
            for i in range(len(row)):
                (is_timeout, value) = row[i]
                if (
                    is_timeout
                    or (i > 0 and row[i - 1][0])
                    or ((i + 1) < len(row) and row[i + 1][0])
                ):
                    new_row.append(value)
                else:
                    new_row.append(None)

            # Normalize by the first value in the sequence, and take the log_2
            first = None
            for i in range(len(new_row)):
                if new_row[i] is not None:
                    if first is None:
                        first = new_row[i]
                        new_row[i] = 1.0
                    elif first != 0:
                        new_row[i] = new_row[i] / first

            row[:] = new_row

        self.ax.set_ylabel("Relative progress")
        self.ax.set_yscale("log")
        self.ax.hlines(
            y=1.0,
            xmin=0,
            xmax=len(selected_runs) - 1,
            colors="grey",
            linestyles="--",
            lw=1,
        )
        self.ax.get_yaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
        loc = mpl.ticker.MultipleLocator(base=0.1)
        self.ax.get_yaxis().set_major_locator(loc)

    def refresh_data_set(self, set_selector):
        self.selected_data_set = set_selector.get_active_id()

        self.runs_store.clear()
        self.cases_store.clear()

        known_cases = dict()
        for run in read_runs(self.selected_data_set):
            self.runs_store.append(run)
            for data in read_cases_data(self.selected_data_set, *run):
                # Insert case name in a dict instead of a set to preserve the original order:
                known_cases[data[0]] = None
        for case_name in known_cases:
            self.cases_store.append([case_name, False, Gdk.RGBA()])

        self.runs_selection.select_all()
        self.cases_selection.select_all()

    def _refresh_data(self):
        (cases, sel_cases) = self.cases_selection.get_selected_rows()
        cases_vals = (cases.get_iter(p) for p in sel_cases)
        cases_vals = {cases.get(it, 0)[0]: (it, []) for it in cases_vals}

        (runs, sel_runs) = self.runs_selection.get_selected_rows()
        sel_runs = [runs.get(runs.get_iter(p), 0, 1) for p in sel_runs]

        x = list(range(len(sel_runs)))
        self.ax.clear()

        self.get_data(sel_runs, cases_vals)

        self.ax.set_xlabel("Case ID")
        self.ax.set_xticks(x, next(zip(*sel_runs)))
        self.lines = []
        for (case_name, (it, values)) in cases_vals.items():
            if all(v is None for v in values):
                cases.set(it, [1], [False])
                continue

            l = self.ax.plot(x, values, "o-", label=case_name)[0]
            l.it = it

            # Set the color in the list view to render the legend
            color = Gdk.RGBA(*mpl.colors.to_rgba(l.get_color()))
            cases.set(it, [1, 2], [True, color])
            self.lines.append(l)

        # Hovering annotation with the name of the case, only displayed when
        # pointed by the mouse.
        self.annot = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(-20, 20),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="w"),
            arrowprops=dict(arrowstyle="->"),
        )
        self.annot.set_visible(False)

        self.canvas.draw_idle()

    def update_annot(self, ind, line):
        x, y = line.get_data()
        self.annot.xy = (x[ind["ind"][0]], y[ind["ind"][0]])
        self.annot.set_text(line.get_label())

    def mouse_hover(self, event):
        if event.inaxes:  # There is only one axis...
            # Find which line we are hovering over (if any):
            #
            # TODO: it would be nice to have a quadtree here to narrow down the
            # lines.
            for line in self.lines:
                cont, ind = line.contains(event)
                if cont:
                    self.selected_line = line
                    self.update_annot(ind, line)
                    self.annot.set_visible(True)
                    self.canvas.draw_idle()
                    return

            if self.annot.get_visible():
                self.selected_line = None
                self.annot.set_visible(False)
                self.canvas.draw_idle()

    def mouse_click(self, event):
        if event.inaxes and self.selected_line:
            self.cases_selection.unselect_all()
            self.cases_selection.select_iter(self.selected_line.it)
            self.canvas.draw_idle()


def main():
    viewer = Viewer()
    Gtk.main()


if __name__ == "__main__":
    main()
