# Internal Packages

Internal packages own PCG runtime behavior behind the command binaries. Keep
package boundaries narrow and document the contract at the package or exported
identifier where another package depends on it.

New packages need a package comment, preferably in `doc.go`. Existing packages
should gain package docs when they are touched for behavior, public contracts,
or operator-facing runtime work.
