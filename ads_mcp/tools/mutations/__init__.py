# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mutation tools for Google Ads API.

This package intentionally does NOT eagerly import its tool-defining submodules.
Each tool is registered on the shared MCP server as a side effect of the
``@mcp.tool()`` decorator running at import time, so importing a module here is
what exposes its tools. server.py imports the submodules conditionally (behind
ADS_MCP_ENABLE_MUTATIONS / ADS_MCP_DIRECT_MUTATIONS) to keep direct-execute
mutations off by default. Importing them here would register them
unconditionally and defeat that gating.
"""
