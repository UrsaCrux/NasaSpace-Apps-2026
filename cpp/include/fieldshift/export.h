// export.h - FS_API marks functions exported from the shared library.
//
// Kept in its own header on purpose: minidoc decides whether a brace opens a
// function body by looking for a closing parenthesis before it, so this macro
// right above the extern "C" block would hide every declaration from minidoc.
#ifndef FIELDSHIFT_EXPORT_H
#define FIELDSHIFT_EXPORT_H

#if defined(_WIN32)
#  define FS_API __declspec(dllexport)
#else
#  define FS_API __attribute__((visibility("default")))
#endif

#endif // FIELDSHIFT_EXPORT_H
