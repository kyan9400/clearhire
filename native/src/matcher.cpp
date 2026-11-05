// Aho–Corasick multi-pattern search with whole-word boundaries, for Python (pybind11).
//
// The C++ twin of backend/src/clearhire/skills/aho.py: same automaton, same boundary rules, same word
// characters, same output order. backend/tests/test_native_parity.py checks that both return identical
// matches; backend/scripts/bench_matcher.py measures the difference in speed.
//
// Text is handled as UTF-32 code points, so offsets equal Python string indices.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <cstdint>
#include <deque>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace py = pybind11;

namespace {

// Letters, digits and "_" in the scripts CVs use. Mirrors is_word_char() in clearhire/text.py.
bool is_word_cp(char32_t cp) {
  if (cp < 0x80) {
    return (cp >= U'0' && cp <= U'9') || (cp >= U'A' && cp <= U'Z') || (cp >= U'a' && cp <= U'z') || cp == U'_';
  }
  return (cp >= 0x00C0 && cp <= 0x024F && cp != 0x00D7 && cp != 0x00F7) || (cp >= 0x0370 && cp <= 0x03FF) ||
         (cp >= 0x0400 && cp <= 0x052F) || (cp >= 0x0531 && cp <= 0x0587) || (cp >= 0x05D0 && cp <= 0x05EA) ||
         (cp >= 0x0620 && cp <= 0x064A) || (cp >= 0x0660 && cp <= 0x0669) || (cp >= 0x06F0 && cp <= 0x06F9) ||
         (cp >= 0x0E00 && cp <= 0x0E7F) || (cp >= 0x1E00 && cp <= 0x1EFF) || (cp >= 0x3040 && cp <= 0x30FF) ||
         (cp >= 0x4E00 && cp <= 0x9FFF) || (cp >= 0xAC00 && cp <= 0xD7AF);
}

using Match = std::tuple<int, int, int>;  // (pattern index, start, end)

class Matcher {
 public:
  Matcher(const std::vector<std::u32string>& patterns, const std::vector<bool>& prefix)
      : lengths_(patterns.size()), prefix_(prefix) {
    if (prefix.size() != patterns.size()) {
      throw std::invalid_argument("prefix flags must match the patterns");
    }
    new_node();
    for (std::size_t index = 0; index < patterns.size(); ++index) {
      const std::u32string& pattern = patterns[index];
      if (pattern.empty()) {
        throw std::invalid_argument("empty pattern");
      }
      lengths_[index] = static_cast<int>(pattern.size());
      int node = 0;
      for (char32_t cp : pattern) {
        int next = edge(node, cp);
        if (next < 0) {
          next = new_node();
          set_edge(node, cp, next);
        }
        node = next;
      }
      out_[node].push_back(static_cast<int>(index));
    }
    link();
  }

  std::vector<Match> find(const std::u32string& text) const {
    std::vector<Match> matches;
    const int size = static_cast<int>(text.size());
    int node = 0;
    for (int position = 0; position < size; ++position) {
      const char32_t cp = text[position];
      while (node != 0 && edge(node, cp) < 0) {
        node = fail_[node];
      }
      const int next = edge(node, cp);
      node = next < 0 ? 0 : next;
      const std::vector<int>& outputs = out_[node];
      if (outputs.empty()) {
        continue;
      }
      const int end = position + 1;
      for (int index : outputs) {
        const int start = end - lengths_[index];
        if (start > 0 && is_word_cp(text[start - 1])) {
          continue;
        }
        if (!prefix_[index] && end < size && is_word_cp(text[end])) {
          continue;
        }
        matches.emplace_back(index, start, end);
      }
    }
    return matches;
  }

  std::size_t nodes() const { return fail_.size(); }

 private:
  // ASCII transitions in a dense table (most skill aliases are ASCII), others in a hash map.
  std::vector<std::array<int32_t, 128>> ascii_;
  std::vector<std::unordered_map<char32_t, int32_t>> other_;
  std::vector<int> fail_;
  std::vector<std::vector<int>> out_;
  std::vector<int> lengths_;
  std::vector<bool> prefix_;

  int new_node() {
    std::array<int32_t, 128> empty;
    empty.fill(-1);
    ascii_.push_back(empty);
    other_.emplace_back();
    fail_.push_back(0);
    out_.emplace_back();
    return static_cast<int>(fail_.size()) - 1;
  }

  int edge(int node, char32_t cp) const {
    if (cp < 128) {
      return ascii_[node][cp];
    }
    const auto& map = other_[node];
    const auto found = map.find(cp);
    return found == map.end() ? -1 : found->second;
  }

  void set_edge(int node, char32_t cp, int child) {
    if (cp < 128) {
      ascii_[node][cp] = child;
    } else {
      other_[node][cp] = child;
    }
  }

  std::vector<std::pair<char32_t, int>> children(int node) const {
    std::vector<std::pair<char32_t, int>> out;
    for (char32_t cp = 0; cp < 128; ++cp) {
      if (ascii_[node][cp] >= 0) {
        out.emplace_back(cp, ascii_[node][cp]);
      }
    }
    for (const auto& item : other_[node]) {
      out.emplace_back(item.first, item.second);
    }
    return out;
  }

  // Breadth-first failure links; each node's outputs include those of its failure node.
  void link() {
    std::deque<int> queue;
    for (const auto& child : children(0)) {
      queue.push_back(child.second);
    }
    while (!queue.empty()) {
      const int node = queue.front();
      queue.pop_front();
      for (const auto& [cp, child] : children(node)) {
        queue.push_back(child);
        int fail = fail_[node];
        while (fail != 0 && edge(fail, cp) < 0) {
          fail = fail_[fail];
        }
        const int target = edge(fail, cp);
        fail_[child] = (target < 0 || target == child) ? 0 : target;
        const std::vector<int>& inherited = out_[fail_[child]];
        out_[child].insert(out_[child].end(), inherited.begin(), inherited.end());
      }
    }
    for (auto& outputs : out_) {
      std::sort(outputs.begin(), outputs.end());
    }
  }
};

}  // namespace

PYBIND11_MODULE(clearhire_native, module) {
  module.doc() = "C++ Aho-Corasick skill matcher for Clearhire";
  module.attr("__version__") = "0.1.0";
  py::class_<Matcher>(module, "Matcher")
      .def(py::init<const std::vector<std::u32string>&, const std::vector<bool>&>(), py::arg("patterns"),
           py::arg("prefix"))
      .def("find", &Matcher::find, py::arg("text"), py::call_guard<py::gil_scoped_release>(),
           "All whole-word matches as (pattern index, start, end), ordered by end, then pattern index.")
      .def_property_readonly("nodes", &Matcher::nodes);
}
