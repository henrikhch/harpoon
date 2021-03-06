# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import image_objs as objs
from harpoon.option_spec import command_objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.spec_base import NotSpecified
from input_algorithms.meta import Meta
import datetime
import tarfile
import mock
import os

describe HarpoonCase, "Image object":
	before_each:
		self.mtime = int(datetime.datetime.now().strftime("%s"))
		self.silent_build = False

	def make_image(self, options):
		config_root = self.make_temp_dir()
		harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), {"silent_build": self.silent_build})
		if "harpoon" not in options:
			options["harpoon"] = harpoon
		return HarpoonSpec().image_spec.normalise(Meta({"mtime": self.mtime, "_key_name_1": "awesome_image", "config_root": config_root}, []), options)

	describe "Docker file":
		it "Creates a dockerfile object from the commands":
			image = self.make_image({"commands": ["FROM ubuntu:14.04"]})
			docker_file = image.docker_file
			self.assertIs(type(docker_file), objs.DockerFile)
			self.assertEqual(docker_file.mtime, self.mtime)
			self.assertEqual(docker_file.docker_lines, ["FROM ubuntu:14.04"])

	describe "Context":
		describe "make_context":
			it "uses ContextBuilder with self.docker_file and adds the dockerfile to the tarfile":
				image = self.make_image({"commands": ["FROM ubuntu:14.04"]})
				add_docker_file_to_tarfile = mock.Mock(name="add_docker_file_to_tarfile")

				builder = mock.MagicMock(name="builder")
				docker_file = mock.Mock(name="docker_file")
				docker_file.docker_lines = image.docker_file.docker_lines
				extra_context = mock.Mock(name="extra_context")
				context_options = mock.Mock(name="context_options")

				t = mock.Mock(name="t")
				ctxt = mock.Mock(name="context", t=t)
				make_context_manager_called = mock.Mock(name="context_manager()")
				make_context_manager = mock.MagicMock(name="context_manager", return_value=make_context_manager_called)
				make_context_manager_called.__enter__ = mock.Mock(name="__enter__", return_value = ctxt)
				make_context_manager_called.__exit__ = mock.Mock(name="__exit__", return_value=None)

				with mock.patch.object(builder, "make_context", make_context_manager, create=True):
					with mock.patch.object(command_objs.Commands, "extra_context", extra_context):
						with mock.patch.multiple(image, docker_file=docker_file, context=context_options, add_docker_file_to_tarfile=add_docker_file_to_tarfile):
							with mock.patch("harpoon.option_spec.image_objs.ContextBuilder", mock.Mock(name="ContextBuilder", return_value=builder)):
								with image.make_context() as ct:
									self.assertIs(ct, ctxt)

				add_docker_file_to_tarfile.assert_called_once_with(docker_file, t)
				make_context_manager.assert_called_once_with(context_options, silent_build=self.silent_build, extra_context=extra_context)

			it "uses ContextBuilder with docker_file passed in":
				image = self.make_image({"commands": ["FROM ubuntu:14.04"]})
				add_docker_file_to_tarfile = mock.Mock(name="add_docker_file_to_tarfile")

				builder = mock.MagicMock(name="builder")
				docker_file = mock.Mock(name="docker_file")
				docker_file.docker_lines = image.docker_file.docker_lines
				extra_context = mock.Mock(name="extra_context")
				context_options = mock.Mock(name="context_options")

				t = mock.Mock(name="t")
				ctxt = mock.Mock(name="context", t=t)
				make_context_manager_called = mock.Mock(name="context_manager()")
				make_context_manager = mock.MagicMock(name="context_manager", return_value=make_context_manager_called)
				make_context_manager_called.__enter__ = mock.Mock(name="__enter__", return_value = ctxt)
				make_context_manager_called.__exit__ = mock.Mock(name="__exit__", return_value=None)

				with mock.patch.object(builder, "make_context", make_context_manager, create=True):
					with mock.patch.object(command_objs.Commands, "extra_context", extra_context):
						with mock.patch.multiple(image, context=context_options, add_docker_file_to_tarfile=add_docker_file_to_tarfile):
							with mock.patch("harpoon.option_spec.image_objs.ContextBuilder", mock.Mock(name="ContextBuilder", return_value=builder)):
								with image.make_context(docker_file=docker_file) as ct:
									self.assertIs(ct, ctxt)

				add_docker_file_to_tarfile.assert_called_once_with(docker_file, t)
				make_context_manager.assert_called_once_with(context_options, silent_build=self.silent_build, extra_context=extra_context)

		describe "add_docker_file_to_tarfile":
			it "adds a temp file with the docker_lines in it to the docker file":
				image = self.make_image({"commands": ["RUN one", "RUN two"]})

				tar = tarfile.open(self.make_temp_file().name, "w")
				image.add_docker_file_to_tarfile(image.docker_file, tar)
				tar.close()

				self.assertTarFileContent(tar.name, {"./Dockerfile": (self.mtime, "RUN one\nRUN two")})

