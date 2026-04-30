# the-black-goat-stdlib

Baseline tools that ship with `the-black-goat`. Registered under the `stdlib`
plugin namespace.

- `stdlib.now` — current UTC timestamp.
- `stdlib.sleep` — block for N seconds.
- `stdlib.echo` — return the input message unchanged.

These exist mostly to dogfood the plugin contract; consumers are expected to
write their own plugins for anything serious.
