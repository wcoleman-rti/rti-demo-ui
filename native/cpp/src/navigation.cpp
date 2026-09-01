#include "navigation.hpp"

#include <rti_demo_ui_native/native_webview.hpp>

namespace rti::demo::ui::native::detail {

std::string origin(const std::string& url) {
    const auto scheme = url.find("://");
    const auto authority = scheme == std::string::npos ? 0 : scheme + 3;
    const auto path = url.find_first_of("/?#", authority);
    if (scheme == std::string::npos || url.compare(0, scheme, "http") != 0 ||
        authority == url.size()) {
        throw NativeWebviewError(
            "native window URL must be an HTTP loopback origin");
    }
    return path == std::string::npos ? url : url.substr(0, path);
}

bool same_origin(const std::string& url, const std::string& allowed_origin) {
    try {
        return origin(url) == allowed_origin;
    } catch (const NativeWebviewError&) {
        return false;
    }
}

}  // namespace rti::demo::ui::native::detail
