/* Copyright (C) Real Time Logic LLC, 2026. */
#ifndef BAS_RT1020_OPTIONS
#define BAS_RT1020_OPTIONS
/* Only overrides; BAS, ThreadX and Xedge supply their defaults afterward. */
#define BA_ENABLE_HTTP_THREAD_POOL 1
#define BA_ENABLE_HTTP_UPLOAD 1
#define BA_ENABLE_WEBDAV 1
#define BA_ENABLE_JSON 1
#define BA_ENABLE_JSON_USER_DATABASE 1
#define BA_ENABLE_UDP 1
#define BA_ENABLE_MDNS 1
#define BA_ENABLE_MDNS_LUA 1
#define BA_ENABLE_EMBEDDED_CA 1
#define BA_ENABLE_TPM 1
#define BA_ENABLE_LUA_DEBUGGER 1
#define BA_ENABLE_LUA_OPCUA 1
#define BA_ENABLE_UBJSON 1
#define BA_ENABLE_REVERSE_CONNECTION 1
#define BA_ENABLE_REVERSE_PROXY 1
#define BA_THREAD_STACK_SIZE 65536
#define BA_NX_DNS
#endif
