
import plugin

####################################################################################################

if __name__ == "__main__":
	live = plugin.Live()
	live.update()
	live.integrate()

	boxes = plugin.Boxes()
	boxes.update()

