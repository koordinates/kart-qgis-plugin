import os

from qgis.PyQt.QtGui import QIcon

_pluginPath = os.path.split(os.path.dirname(__file__))[0]


def icon(f):
    return QIcon(os.path.join(_pluginPath, "img", f))


abortIcon = icon("abort.png")
aboutIcon = icon("info.png")
addedIcon = icon("add.png")
addRepoIcon = icon("addrepo.png")
addtoQgisIcon = icon("openinqgis.png")
checkoutIcon = icon("checkout.png")
cloneRepoIcon = icon("clone.png")
commitIcon = icon("commit.png")
createBranchIcon = icon("createbranch.png")
createRepoIcon = icon("createrepo.png")
crossIcon = icon("cross.png")
datasetIcon = icon("dataset.png")
deleteIcon = icon("delete.png")
diffIcon = icon("changes.png")
discardIcon = icon("reset.png")
featureIcon = icon("layer.png")
importIcon = icon("import.png")
kartIcon = icon("kart.png")
layerIcon = icon("layer.png")
logIcon = icon("log.png")
mergeIcon = icon("merge.png")
modifiedIcon = icon("edit.png")
patchIcon = icon("patch.png")
propertiesIcon = icon("info.png")
pullIcon = icon("pull.png")
pushIcon = icon("push.png")
refreshIcon = icon("refresh.png")
removeIcon = icon("remove.png")
repoIcon = icon("repository.png")
resetIcon = icon("reset.png")
resolveIcon = icon("resolve.png")
restoreIcon = icon("checkout.png")
settingsIcon = icon("settings.png")
tableIcon = icon("table.png")
vectorDatasetIcon = icon("vector-polyline.png")
