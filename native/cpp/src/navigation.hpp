#pragma once

#include <string>

namespace rti::demo::ui::native::detail {

std::string origin(const std::string& url);
bool same_origin(const std::string& url, const std::string& allowed_origin);

}  // namespace rti::demo::ui::native::detail
