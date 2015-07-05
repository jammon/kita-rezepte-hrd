function gangauswaehlen(gang, titel, id) {
    $('#'+gang).text(titel).next().attr('value', id)
}