# coding: spec

from harpoon.collector import Collector

from tests.helpers import HarpoonCase

from input_algorithms.dictobj import dictobj
from delfick_app import command_output
from option_merge import MergedOptions
from textwrap import dedent
from getpass import getpass
import mock
import json
import os

describe HarpoonCase, "Collector":
    describe "clone":
        it "has a new harpoon object":
            configuration = {"harpoon": {"chosen_image": "blah"}, "images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                collector = Collector()
                collector.prepare(filename, {"harpoon": {}, "bash": None, "command": None})
                collector2 = collector.clone({"chosen_image": "other"})

                self.assertNotEqual(collector.configuration["harpoon"], collector2.configuration["harpoon"])
                self.assertEqual(collector.configuration["harpoon"].chosen_image, "blah")
                self.assertEqual(collector2.configuration["harpoon"].chosen_image, "other")

    describe "prepare":
        it "complains if there is no images":
            configuration = {}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                with self.fuzzyAssertRaisesError(Collector.BadConfigurationErrorKls, "Didn't find any images in the configuration"):
                    Collector().prepare(filename, {})

        it "adds some items to the configuration from the cli_args":
            bash = "bash command"
            extra = "extra commands after the --"
            command = "Command command"

            configuration = {"images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                collector = Collector()
                raw_config = collector.collect_configuration(filename)
                for thing in ("configuration", "$@", "bash", "command", "harpoon", "collector", "getpass", "cli_args"):
                    assert thing not in raw_config, "expected {0} to not be in configuration".format(thing)

                cli_args = {"harpoon": {"extra": extra}, "bash": bash, "command": command}
                collector.prepare(filename, cli_args)

                # Done by option_merge
                self.assertEqual(collector.configuration["getpass"], getpass)
                self.assertEqual(collector.configuration["cli_args"].as_dict(), cli_args)
                self.assertEqual(collector.configuration["collector"], collector)
                self.assertEqual(collector.configuration["config_root"], os.path.dirname(filename))

                # Done by bespin
                self.assertEqual(collector.configuration["$@"], extra)
                self.assertEqual(collector.configuration["bash"], bash)
                self.assertEqual(collector.configuration["command"], command)
                self.assertEqual(collector.configuration["harpoon"]["extra"], extra)

        it "adds task_runner from a TaskFinder to the configuration and finds tasks":
            task_finder = mock.Mock(name="task_finder")
            FakeTaskFinder = mock.Mock(name="TaskFinder", return_value=task_finder)
            configuration = {"images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                with mock.patch("harpoon.collector.TaskFinder", FakeTaskFinder):
                    collector = Collector()
                    cli_args = {"harpoon": {}, "bash": None, "command": None}
                    collector.prepare(filename, cli_args)
                    task_finder.find_tasks.assert_called_once_with({})

                    self.assertEqual(len(task_finder.task_runner.mock_calls), 0)
                    collector.configuration["task_runner"]("blah")
                    task_finder.task_runner.assert_called_once_with("blah")

                    FakeTaskFinder.assert_called_once_with(collector, cli_args)

    describe "Configuration":
        describe "start configuration":
            it "Returns a MergedOptions that doesn't prefix dictobjs":
                class Thing(dictobj):
                    fields = ["one", "two"]

                thing = Thing(1, 2)
                options = Collector().start_configuration()
                options.update({"three": {"four": {"5": "6"}}, "seven": thing})

                self.assertIs(type(options["three"]), MergedOptions)
                self.assertEqual(options["three"].as_dict(), {"four": {"5": "6"}})

                self.assertIs(type(options["seven"]), Thing)
                self.assertEqual(options["seven"], {"one": 1, "two": 2})

        describe "Reading a file":
            it "reads a yaml file and returns it as a dictionary":
                config = dedent("""
                    ---

                    one: 1
                    two:
                        three: 3
                        four: 4
                    five: |
                        six
                        seven
                        eight
                    nine: >
                        ten
                        eleven
                        twelve
                """).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    readed = collector.read_file(filename)
                    self.assertEqual(readed, {"one": 1, "two": {"three": 3, "four": 4}, "five": "six\nseven\neight\n", "nine": "ten eleven twelve"})

            it "complains about scanner errors":
                config = dedent("""
                    ---

                    five: |>
                        six
                        seven
                        eight
                """).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    with self.fuzzyAssertRaisesError(collector.BadFileErrorKls, "Failed to read yaml", location=filename, error_type="ScannerError", error="expected chomping or indentation indicators, but found '>'  in \"{0}\", line 3, column 8".format(filename)):
                        readed = collector.read_file(filename)

            it "complains about parser errors":
                config = dedent("""
                    ---

                    five: {one
                """).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    with self.fuzzyAssertRaisesError(collector.BadFileErrorKls, "Failed to read yaml", location=filename, error_type="ParserError", error="expected ',' or '}}', but got '<stream end>'  in \"{0}\", line 3, column 11".format(filename)):
                        readed = collector.read_file(filename)

        describe "Getting committime or mtime":
            it "uses git if context.use_git else just gets mtime":
                with self.a_temp_dir() as directory:
                    assert command_output("git init .", cwd=directory)[1] is 0
                    assert command_output("touch blah", cwd=directory)[1] is 0
                    assert command_output("git add blah", cwd=directory)[1] is 0
                    os.utime(os.path.join(directory, "blah"), (13456789, 13456789))
                    assert command_output("git commit -am 'stuff'", cwd=directory)[1] is 0
                    output, status = command_output("git log --pretty=%at", cwd=directory)
                    assert status is 0

                    expected = int(output[0])
                    self.assertNotEqual(expected, 13456789)

                    collector = Collector()

                    ctxt = mock.Mock(name="context")
                    ctxt.use_git = True
                    self.assertEqual(collector.get_committime_or_mtime(ctxt, os.path.join(directory, "blah")), expected)

                    # And without git
                    ctxt.use_git = False
                    self.assertEqual(collector.get_committime_or_mtime(ctxt, os.path.join(directory, "blah")), 13456789)

        describe "Adding configuration":
            it "adds in an mtime function":
                collector = Collector()
                configuration = collector.start_configuration()
                collect_another_source = mock.Mock(name="collect_another_source")
                src = mock.Mock(name="src")
                result = {"one": 1}

                collector.add_configuration(configuration, collect_another_source, {}, result, src)
                self.assertEqual(configuration["one"], 1)
                self.assertEqual(configuration.storage.data[0][2], src)

                ctxt = mock.Mock(name="context")
                get_committime_or_mtime = mock.Mock(name="get_committime_or_mtime", return_value=13456789)
                with mock.patch.object(collector, "get_committime_or_mtime", get_committime_or_mtime):
                    self.assertEqual(configuration["mtime"](ctxt), 13456789)
                get_committime_or_mtime.assert_called_once_with(ctxt, src)

            it "collects files in folders specified by images.__images_from__":
                root, folders = self.setup_directory({"one": {"two": {"three.yml":"", "four.yml":""}, "five": [], "six": {"seven.yml":""}, "eight.yml": ""}, "two": {"notseen.yml":""}})
                collect_another_source = mock.Mock(name="collect_another_source")

                collector = Collector()
                configuration = collector.start_configuration()
                done = {}
                result = {"images": {"__images_from__": [folders["one"]["/folder/"]]}}
                src = mock.Mock(name="src")
                collector.add_configuration(configuration, collect_another_source, done, result, src)

                self.assertEqual(collect_another_source.mock_calls
                    , [ mock.call(folders["one"]["eight.yml"]["/file/"], prefix=["images", "eight"], extra={"mtime": mock.ANY})
                      , mock.call(folders["one"]["two"]['four.yml']["/file/"], prefix=["images", "four"], extra={"mtime": mock.ANY})
                      , mock.call(folders["one"]["two"]['three.yml']["/file/"], prefix=["images", "three"], extra={"mtime": mock.ANY})
                      , mock.call(folders["one"]["six"]['seven.yml']["/file/"], prefix=["images", "seven"], extra={"mtime": mock.ANY})
                      ]
                    )

            it "successfully prefixes included __images_from__":
                config = json.dumps({"commands": "FROM ubuntu:14.04"})
                root, folders = self.setup_directory({"one": {"two": {"three.yml":config, "four.yml":config}, "five": [], "six": {"seven.yml":config}}, "two": {"notseen.yml":config}})
                configuration = {"images": {"__images_from__": folders["one"]["/folder/"]}}
                with self.a_temp_file(json.dumps(configuration)) as filename:
                    collector = Collector()
                    collector.prepare(filename, {"harpoon": {}, "bash": None, "command": None})
                    cfg = json.loads(config)
                    cfg["mtime"] = mock.ANY

                    cfg_three = dict(cfg)
                    cfg_four = dict(cfg)
                    cfg_seven = dict(cfg)

                    cfg_three["config_root"] = folders["one"]["two"]["/folder/"]
                    cfg_four["config_root"] = folders["one"]["two"]["/folder/"]
                    cfg_seven["config_root"] = folders["one"]["six"]["/folder/"]
                    self.assertEqual(collector.configuration["images"].as_dict(), {"three": cfg_three, "four": cfg_four, "seven": cfg_seven})