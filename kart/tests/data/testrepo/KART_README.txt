This directory is a Kart repository.

It may look empty, but every version of every datasets that this repository
contains is stored in Kart's internal format in the ".kart" hidden subdirectory.
To check if a directory is a Kart repository and see what is stored, run:

kart status

It may simply output "Empty repository. Use kart import to add some data".
Follow the tutorial at https://kartproject.org for help getting started with Kart.

Some more helpful commands for getting a broad view of what a Kart repository
contains are:

kart log      - show the history of what has been committed to this repository.
kart data ls  - show the names of every dataset in this repository.

This directory is the default location where Kart puts the repository's working
copy, which is created as soon as there is some data to put in it. However
the working copy can also be configured to be somewhere else, and may not be
a file at all. To see the working copy's location, run this command:

kart config kart.workingcopy.location

