/*
 * Load hetero_dram::Params from the flat JSON object that
 * targets/hetero/dram_presets.py emits ({"key": int | "string", ...}).
 *
 * Only that flat shape is accepted -- no nesting, no arrays -- which is all the
 * preset dump ever produces, so a few lines of scanning beat a JSON dependency
 * for two small command-line tools.
 */

#pragma once

#include "../../targets/hetero/dram_core.hpp"

#include <cctype>
#include <fstream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>

namespace hetero_dram
{

inline std::map<std::string, std::string> read_flat_json(const std::string &path)
{
    std::ifstream f(path);
    if (!f) throw std::runtime_error("cannot open " + path);
    std::stringstream ss;
    ss << f.rdbuf();
    std::string s = ss.str();

    std::map<std::string, std::string> out;
    size_t i = 0;
    auto skip = [&]() { while (i < s.size() && (isspace((unsigned char)s[i]) || s[i] == ',' || s[i] == '{' || s[i] == '}')) i++; };
    auto str = [&]() {
        if (s[i] != '"') throw std::runtime_error(path + ": expected a string");
        size_t j = s.find('"', i + 1);
        std::string v = s.substr(i + 1, j - i - 1);
        i = j + 1;
        return v;
    };
    for (skip(); i < s.size(); skip())
    {
        std::string key = str();
        while (i < s.size() && (isspace((unsigned char)s[i]) || s[i] == ':')) i++;
        if (s[i] == '"')
        {
            out[key] = str();
        }
        else
        {
            size_t j = i;
            while (j < s.size() && (isalnum((unsigned char)s[j]) || s[j] == '-' || s[j] == '.')) j++;
            out[key] = s.substr(i, j - i);
            i = j;
        }
    }
    return out;
}

inline Params load_params(const std::string &path)
{
    std::map<std::string, std::string> kv = read_flat_json(path);
    Params p;
    for (auto &f : int_fields())
    {
        auto it = kv.find(f.first);
        if (it == kv.end()) continue;
        std::string v = it->second;
        p.*(f.second) = (v == "true") ? 1 : (v == "false") ? 0 : std::stoll(v);
    }
    for (auto &f : str_fields())
    {
        auto it = kv.find(f.first);
        if (it != kv.end()) p.*(f.second) = it->second;
    }
    return p;
}

} // namespace hetero_dram
