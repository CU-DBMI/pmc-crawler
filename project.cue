package main

import (
	"dagger.io/dagger"
	"universe.dagger.io/docker"
)

dagger.#Plan & {

	client: {
		filesystem: {
			"./": read: contents:                        dagger.#FS
			"./smartsheet-notebooks": write: contents: actions.clean.black.export.directories."/workdir/smartsheet-notebooks"
			"./project.cue": write: contents:            actions.clean.cue.export.files."/workdir/project.cue"
		}
	}
	python_version: string | *"3.9"
	poetry_version: string | *"1.1.13"

	actions: {
		// referential build for base python image
		_python_pre_build: docker.#Build & {
			steps: [
				docker.#Pull & {
					source: "python:" + python_version
				},
				docker.#Run & {
					command: {
						name: "mkdir"
						args: ["/workdir"]
					}
				},
				docker.#Copy & {
					contents: client.filesystem."./".read.contents
					source:   "./pyproject.toml"
					dest:     "/workdir/pyproject.toml"
				},
				docker.#Copy & {
					contents: client.filesystem."./".read.contents
					source:   "./poetry.lock"
					dest:     "/workdir/poetry.lock"
				},
				docker.#Run & {
					workdir: "/workdir"
					command: {
						name: "pip"
						args: ["install", "--no-cache-dir", "poetry==" + poetry_version]
					}
				},
				docker.#Set & {
					config: {
						env: ["POETRY_VIRTUALENVS_CREATE"]: "false"
					}
				},
				docker.#Run & {
					workdir: "/workdir"
					command: {
						name: "poetry"
						args: ["install", "--no-interaction", "--no-ansi"]
					}
				},
			]
		}
		// python build for actions in this plan
		_python_build: docker.#Build & {
			steps: [
				docker.#Copy & {
					input:    _python_pre_build.output
					contents: client.filesystem."./".read.contents
					source:   "./"
					dest:     "/workdir"
				},
			]
		}
		// cuelang pre build
		_cue_pre_build: docker.#Build & {
			steps: [
				docker.#Pull & {
					source: "golang:latest"
				},
				docker.#Run & {
					command: {
						name: "mkdir"
						args: ["/workdir"]
					}
				},
				docker.#Run & {
					command: {
						name: "go"
						args: ["install", "cuelang.org/go/cmd/cue@latest"]
					}
				},
			]
		}
		// cuelang build for actions in this plan
		_cue_build: docker.#Build & {
			steps: [
				docker.#Copy & {
					input:    _cue_pre_build.output
					contents: client.filesystem."./".read.contents
					source:   "./project.cue"
					dest:     "/workdir/project.cue"
				},
			]
		}
		// applied code and/or file formatting
		clean: {
			// remove jupyter notebook output data
			remove_jupyter_output: docker.#Run & {
				input:   _python_build.output
				workdir: "/workdir"
				command: {
					name: "find"
					args: ["/workdir/smartsheet-notebooks", "-name", "*.ipynb",
						"-exec", "poetry", "run", "python", "-m", "jupyter", "nbconvert",
						"--clear-output", "--inplace",
						"{}", "+"]
				}
			}
			// sort python imports with isort
			isort: docker.#Run & {
				input:   remove_jupyter_output.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "nbqa", "isort", "smartsheet-notebooks/"]
				}
			}
			// code style formatting with black
			black: docker.#Run & {
				input:   isort.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "black", "smartsheet-notebooks/"]
				}
				export: {
					directories: {
						"/workdir/smartsheet-notebooks": _
					}
				}
			}
			// code formatting for cuelang
			cue: docker.#Run & {
				input:   _cue_build.output
				workdir: "/workdir"
				command: {
					name: "cue"
					args: ["fmt", "/workdir/project.cue"]
				}
				export: {
					files: "/workdir/project.cue": _
				}
			}
		}
		// lint
		lint: {
			// mypy static type check
			mypy: {
				output: run.output
				// mypy has trouble with dashed-name "-" directories, 
				// so we copy the contents for mypy focus to similar dir
				copy: docker.#Run & {
					input:   _python_build.output
					workdir: "/workdir"
					command: {
						name: "cp"
						args: ["-r", "/workdir/smartsheet-notebooks/", "/workdir/smartsheet_notebooks/"]
					}
				}
				// actual mypy check
				run: docker.#Run & {
					input:   copy.output
					workdir: "/workdir"
					command: {
						name: "poetry"
						args: ["run", "nbqa", "mypy", "smartsheet_notebooks/", "--ignore-missing-imports"]
					}
				}
			}
			// isort (imports) formatting check
			isort: docker.#Run & {
				input:   mypy.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "nbqa", "isort", "smartsheet-notebooks/", "--check", "--diff"]
				}
			}
			// black formatting check
			black: docker.#Run & {
				input:   isort.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "nbqa", "black", "smartsheet-notebooks/", "--check"]
				}
			}
			// pylint checks
			pylint: docker.#Run & {
				input:   black.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "nbqa", "pylint", "smartsheet-notebooks/"]
				}
			}
			// safety security vulnerabilities check
			safety: docker.#Run & {
				input:   pylint.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "safety", "check"]
				}
			}
			// bandit security vulnerabilities check
			bandit: docker.#Run & {
				input:   safety.output
				workdir: "/workdir"
				command: {
					name: "poetry"
					args: ["run", "nbqa", "bandit", "smartsheet-notebooks/", "-r"]
				}
			}
		}
	}
}
