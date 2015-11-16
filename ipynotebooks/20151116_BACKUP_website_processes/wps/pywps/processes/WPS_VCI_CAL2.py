
# coding: utf-8

# # VCI calculation process
# This process intend to calculate the Vegetation Condition index (VCI) for a specific area. The fomula of the index is:
# VCI =NDVI/(max(NDVI)-min(NDVI))
# where the NDVI is Normalized Difference Vegetation Index.
# This is a WPS process served by PyWPS. 
# 
# Input:
# bBox:a rectangle box which specifies the processing area.
# date: a date string specifies the date to be calculated. The date format should be "YYYY-MM-DD".
# 
# Output:
# file:
# format:
# 
# The process internally retrieves NDVI data set from a rasdaman database.
# 
# Client side execute script:
# http://localhost/cgi-bin/pywps.cgi?service=wps&version=1.0.0&request=execute&identifier=WPS_VCI_CAL&datainputs=[date=2005-02-06;bbox=50,10,120,60]&responsedocument=image=@asReference=true

# In[1]:

from pywps.Process import WPSProcess 
import logging
import os
import sys
import urllib
from osgeo import gdal
import numpy
import numpy.ma as ma
from lxml import etree
from datetime import datetime
import matplotlib
matplotlib.use('AGG')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import cStringIO
from PIL import Image
import glob
import subprocess

def make_colormap(seq):
    """Return a LinearSegmentedColormap
    seq: a sequence of floats and RGB-tuples. The floats should be increasing
    and in the interval (0,1).
    """
    seq = [(None,) * 3, 0.0] + list(seq) + [1.0, (None,) * 3]
    cdict = {'red': [], 'green': [], 'blue': []}
    for i, item in enumerate(seq):
        if isinstance(item, float):
            r1, g1, b1 = seq[i - 1]
            r2, g2, b2 = seq[i + 1]
            cdict['red'].append([item, r1, r2])
            cdict['green'].append([item, g1, g2])
            cdict['blue'].append([item, b1, b2])
    return mcolors.LinearSegmentedColormap('CustomMap', cdict)
c = mcolors.ColorConverter().to_rgb

phase = make_colormap([c('#781800'), c('#B34700'),0.1, c('#B34700'), c('#F09400'),0.2, c('#F09400'), c('#FFBE3B'), 0.3, 
                       c('#FFBE3B'), c('#FFD88A'),0.4, c('#FFD88A'), c('#FFFFFF'),0.5, c('#FFFFFF'), c('#B6D676'), 0.6,
                       c('#B6D676'), c('#8BBA2D'),0.7, c('#8BBA2D'), c('#60A100'),0.8, c('#60A100'), c('#1B8500'), 0.9,
                       c('#1B8500'), c('#006915')])

ndvi_cmap = make_colormap([c('#E9DDD1'), c('#757F1F'), 0.5, c('#757F1F'), c('#142B11')])

class Process(WPSProcess):


    def __init__(self):

        ##
        # Process initialization
        WPSProcess.__init__(self,
            identifier = "WPS_VCI_CAL2",
            title="VCI calculation process",
            abstract="""This process intend to calculate the Vegetation Condition index (VCI) for a specific area..""",
            version = "1.0",
            storeSupported = True,
            statusSupported = True)

        ##
        # Adding process inputs
        
        self.boxIn = self.addBBoxInput(identifier="bbox",
                    title="Spatial region")

        self.dateIn = self.addLiteralInput(identifier="date",
                    title = "The date to be calcualted",
                                          type=type(''))

        ##
        # Adding process outputs

        self.dataOut = self.addComplexOutput(identifier="image",
                title="Output VCI image",
                formats =  [{'mimeType':'image/png'}])

        #self.textOut = self.addLiteralOutput(identifier = "text",
         #       title="Output literal data")

    def _VCI_CAL(self,date,spl_arr):
        
        ##request image cube for the specified date and area by WCS.
        #firstly we get the temporal length of avaliable NDVI data from the DescribeCoverage of WCS
        endpoint='http://159.226.117.95:8080/rasdaman/ows'
        field={}
        field['SERVICE']='WCS'
        field['VERSION']='2.0.1'
        field['REQUEST']='DescribeCoverage'
        field['COVERAGEID']='modis_13c1_cov'#'trmm_3b42_coverage_1'
        url_values = urllib.urlencode(field,doseq=True)
        full_url = endpoint + '?' + url_values
        data = urllib.urlopen(full_url).read()
        root = etree.fromstring(data)
        lc = root.find(".//{http://www.opengis.net/gml/3.2}lowerCorner").text
        uc = root.find(".//{http://www.opengis.net/gml/3.2}upperCorner").text
        start_date=int((lc.split(' '))[2])
        end_date=int((uc.split(' '))[2])
        #print [start_date, end_date]
        
        #generate the dates list 
        cur_date=datetime.strptime(date,"%Y-%m-%d")
        startt=145775
        start=datetime.fromtimestamp((start_date-(datetime(1970,01,01)-datetime(1601,01,01)).days)*24*60*60)
        #print start
        tmp_date=datetime(start.year,cur_date.month,cur_date.day)
        if tmp_date > start :
            start=(tmp_date-datetime(1601,01,01)).days
        else: start=(datetime(start.year+1,cur_date.month,cur_date.day)-datetime(1601,01,01)).days
        datelist=range(start+1,end_date-1,365)
        #print datelist
        
        #find the position of the requested date in the datelist
        cur_epoch=(cur_date-datetime(1601,01,01)).days
        cur_pos=min(range(len(datelist)),key=lambda x:abs(datelist[x]-cur_epoch))
        #print ('Current position:',cur_pos)
        #retrieve the data cube
        cube_arr=[]
        for d in datelist:
            field={}
            field['SERVICE']='WCS'
            field['VERSION']='2.0.1'
            field['REQUEST']='GetCoverage'
            field['COVERAGEID']='modis_13c1_cov'#'trmm_3b42_coverage_1'
            field['SUBSET']=['ansi('+str(d)+')',
                             'Lat('+str(spl_arr[1])+','+str(spl_arr[3])+')',
                            'Long('+str(spl_arr[0])+','+str(spl_arr[2])+')']
            field['FORMAT']='image/tiff'
            url_values = urllib.urlencode(field,doseq=True)
            full_url = endpoint + '?' + url_values
            #print full_url
            tmpfilename='test'+str(d)+'.tif'
            f,h = urllib.urlretrieve(full_url,tmpfilename)
            #print h
            ds=gdal.Open(tmpfilename)

            cube_arr.append(ds.ReadAsArray())
            #print d
        
        ##calculate the regional VCI
        cube_arr_ma=ma.masked_equal(numpy.asarray(cube_arr),-3000)
        VCI=(cube_arr_ma[cur_pos,:,:]-numpy.amin(cube_arr_ma,0))*1.0/(numpy.amax(cube_arr_ma,0)-numpy.amin(cube_arr_ma,0))
        
        ##write the result VCI to disk
        # get parameters
        geotransform = ds.GetGeoTransform()
        spatialreference = ds.GetProjection()
        ncol = ds.RasterXSize
        nrow = ds.RasterYSize
        nband = 1

	trans = ds.GetGeoTransform()
	extent = (trans[0], trans[0] + ds.RasterXSize*trans[1],
		  trans[3] + ds.RasterYSize*trans[5], trans[3])

	# Create figure
	fig = plt.imshow(VCI, cmap=phase, vmin=0, vmax=1.0, extent=extent)#vmin=-0.4, vmax=0.4
	plt.axis('off')
	#plt.colorbar()
	fig.axes.get_xaxis().set_visible(False)
	fig.axes.get_yaxis().set_visible(False)

	# Save to string and compress adaptive
	ram = cStringIO.StringIO()    
	plt.savefig(ram, bbox_inches='tight', pad_inches=0, dpi=400, transparent=True)
	#plt.show()
	plt.close()    
	ram.seek(0)
	im = Image.open(ram)
	im2 = im.convert('RGBA', palette=Image.ADAPTIVE)

        # create dataset for output
        #fmt = 'GTiff'
        vciFileName = 'VCI'+cur_date.strftime("%Y%m%d")+'.png'
	im2.save(vciFileName, format='PNG', quality=50)
        #driver = gdal.GetDriverByName(fmt)
        #dst_dataset = driver.Create(vciFileName, ncol, nrow, nband, gdal.GDT_Byte)
        #dst_dataset.SetGeoTransform(geotransform)
        #dst_dataset.SetProjection(spatialreference)
        #dst_dataset.GetRasterBand(1).WriteArray(VCI*200)
        #dst_dataset = None
        return vciFileName
    
    ##
    # Execution part of the process
    def execute(self):

        # Get the box value
        BBOXObject = self.boxIn.getValue()
        CoordTuple = BBOXObject.coords
        
        #Get the date string
        date = self.dateIn.getValue()
        logging.info(CoordTuple)
        logging.info(date)
        
        #Do the WCS request 
        #endpoint='http://159.226.117.95:8080/rasdaman/ows'
        #field={}
        #field['SERVICE']='WCS'
        #field['VERSION']='2.0.1'
        #field['REQUEST']='GetCoverage'
        #field['COVERAGEID']='trmm_3b42_coverage_1'
        #field['SUBSET']=['ansi(\"'+str(date)+'\")',
        #                'Lat('+str(CoordTuple[0][1])+','+str(CoordTuple[1][1])+')',
        #                'Long('+str(CoordTuple[0][0])+','+str(CoordTuple[1][0])+')']
        #field['FORMAT']='image/tiff'
        #url_values = urllib.urlencode(field,doseq=True)
        #full_url = endpoint + '?' + url_values
        #data = urllib.urlretrieve(full_url,'test.tif')

        #date='2013-06-30'
        #spl_arr=[70,30,80,50]
        spl_arr=[CoordTuple[0][0],CoordTuple[0][1],CoordTuple[1][0],CoordTuple[1][1]]
        logging.info(date)
        logging.info(spl_arr)
        vcifn=self._VCI_CAL(date,spl_arr)
        self.dataOut.setValue( vcifn )
        #self.textOut.setValue( self.textIn.getValue() )
        #os.remove(vcifn)
        logging.info(os.getcwd())
        return


