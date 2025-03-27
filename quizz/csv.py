import json
label = [
    ',Appointment',
    ',Awards',
    ',Banking',
    ',Index and ranking',
    ',Economy',
    ',Science and Tech',
    ',Defence',
    ',International',
    ',General',
    ',MoU',
    ',National',
    ',Inauguration',
    ',Sports',
    ',Book and art',
    ',Obituary',
    ',State'
]

with open('dataset2.cssv', 'w', encoding='utf-8') as edit_file:
    with open('dataset.csv', 'r', encoding='utf-8') as csv_file:
        line = csv_file.readlines()
        for line in line:
            indix = 2**16
            for i in label:
                try:
                    index = line.index(i)
                    if index<indix:
                        indix=index
                    if index:
                        print(index, end=' ')
                except:
                    None
            print(line[:indix]+'|'+line[indix+1:])
            edit_file.write(line[:indix]+'|'+line[indix+1:])