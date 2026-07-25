// torchlib-driver — drives Torch as a linked static library instead of via its CLI.
//
// Two jobs:
//
//   1. Gate A. USE_STANDALONE=OFF compiles out Torch's `int main`, so a static-lib
//      build needs an entry point to be testable at all. This is it.
//
//   2. Rehearse Shipwright's soh/soh/Extractor/TorchExtract.cpp. RunOnce() below is
//      the exact sequence the game will use — assign the bare Companion::Instance
//      global, SetVersion, SetPhaseCallback, Init(Binary), catch everything, and
//      stat the output because Process() returns void. If any of those assumptions
//      is wrong we find out here, against a reference archive, rather than in the
//      game with a progress bar spinning.
//
// argv is deliberately compatible with `torch o2r -s S -d D -u V <rom>` so the
// harness scripts can swap this in via TORCH_BIN and not know the difference.
//
//   torchlib-driver o2r -s <srcdir> -d <destdir> -u <version> <rom.z64>
//                       [--second <rom2.z64> <destdir2>]
//
// --second runs a SECOND extraction in the SAME process (Gate A2): a fresh
// Companion into a fresh destdir, which is what SoH does when the user answers
// "Yes" to extracting another ROM. Torch never clears gProcessedFiles, so reusing
// one Companion would silently skip every file on the second pass — this is what
// proves a fresh instance is enough.

#include <atomic>
#include <cstdio>
#include <cstring>
#include <exception>
#include <filesystem>
#include <string>

#include "Companion.h"
#include "factories/BaseFactory.h"

namespace fs = std::filesystem;

static int RunOnce(const std::string& rom, const std::string& src, const std::string& dest,
                   const std::string& version, const char* label) {
    std::atomic<size_t> phases{ 0 };

    try {
        // Mirrors main.cpp's o2r callback. Companion::Instance is a raw global with
        // no getter, defined outside the STANDALONE guard precisely so the static
        // lib carries the storage; factories dereference it unconditionally.
        auto* companion = new Companion(fs::path(rom), ArchiveType::O2R, /*debug*/ false, src, dest);
        Companion::Instance = companion;
        companion->SetVersion(version);

        // One call site (gPhaseCallback(2)), fired once per yml file at the
        // parse->export transition. This is the denominator the in-game progress
        // bar will use, so count them and let the caller check the total.
        companion->SetPhaseCallback([&phases](int) { ++phases; });

        companion->Init(ExportType::Binary);   // Init is the whole run; it calls Process()
    } catch (const std::exception& e) {
        // 127 `throw std::runtime_error` sites in torch/src and nothing catches at
        // the top level — an escape is std::terminate, not an error message.
        fprintf(stderr, "[%s] exception: %s\n", label, e.what());
        return 2;
    } catch (...) {
        fprintf(stderr, "[%s] unknown exception\n", label);
        return 2;
    }

    // Process() returns void and several fatal paths just log and return: no
    // config.yml, ROM hash absent from config.yml, no `config:` node, bad GBI.
    // Without this check a silent no-archive looks like success.
    // config.yml names the output per ROM (oot.o2r, oot-mq.o2r for master quest).
    fs::path out;
    for (const auto& entry : fs::directory_iterator(dest)) {
        if (entry.path().extension() == ".o2r") {
            out = entry.path();
            break;
        }
    }
    if (out.empty()) {
        fprintf(stderr, "[%s] no .o2r produced in %s\n", label, dest.c_str());
        return 3;
    }

    fprintf(stderr, "[%s] ok: %s (%ju bytes), phases=%zu\n", label, out.c_str(),
            (uintmax_t)fs::file_size(out), phases.load());
    return 0;
}

static void Usage(const char* argv0) {
    fprintf(stderr,
            "usage: %s o2r -s <srcdir> -d <destdir> -u <version> <rom.z64>\n"
            "            [--second <rom2.z64> <destdir2>]\n",
            argv0);
}

int main(int argc, char** argv) {
    std::string src, dest, version, rom;
    std::string secondRom, secondDest;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto next = [&](const char* what) -> std::string {
            if (i + 1 >= argc) {
                fprintf(stderr, "missing argument after %s\n", what);
                exit(1);
            }
            return argv[++i];
        };

        if (arg == "o2r") {
            continue;   // accepted for CLI compatibility; O2R is the only mode here
        } else if (arg == "-s" || arg == "--srcdir") {
            src = next("-s");
        } else if (arg == "-d" || arg == "--destdir") {
            dest = next("-d");
        } else if (arg == "-u" || arg == "--version") {
            version = next("-u");
        } else if (arg == "--second") {
            secondRom = next("--second");
            secondDest = next("--second <rom>");
        } else if (!arg.empty() && arg[0] == '-') {
            fprintf(stderr, "unknown option: %s\n", arg.c_str());
            Usage(argv[0]);
            return 1;
        } else {
            rom = arg;
        }
    }

    if (rom.empty() || src.empty() || dest.empty()) {
        Usage(argv[0]);
        return 1;
    }

    if (const int rc = RunOnce(rom, src, dest, version, "first"); rc != 0) {
        return rc;
    }

    if (!secondRom.empty()) {
        // Deliberately NOT reusing the first Companion — see the header comment.
        if (const int rc = RunOnce(secondRom, src, secondDest, version, "second"); rc != 0) {
            return rc;
        }
    }

    return 0;
}
